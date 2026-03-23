---
phase: design
title: Concurrency & Performance Optimization
description: Architecture for handling concurrent requests and reducing per-request latency
created: 2026-03-22
status: Proposal
---

# Concurrency & Performance Optimization

## 1. Current Performance Baseline

From T4.2 accuracy test (100 quiz questions, 10 topics × 10 questions):

| Stage                             | Time                | Notes                          |
| --------------------------------- | ------------------- | ------------------------------ |
| Generation (10Q per pipeline run) | ~52-208s per topic  | Sequential LLM calls           |
| Worst case single topic           | 813s                | "Số phức" — 3 retry iterations |
| **Total 100Q generation**         | **2019s (~34 min)** | 10 sequential pipeline runs    |
| Evaluation (100Q)                 | 334s                | Sequential structured output   |
| **Total**                         | **2353s (~39 min)** |                                |

### LLM Call Chain Per Pipeline Run (10Q quiz-only)

| Node             | Calls  | Model                         | Purpose            | Est. Time    |
| ---------------- | ------ | ----------------------------- | ------------------ | ------------ |
| Supervisor       | 1      | gemini-3.1-flash-lite         | Classification     | ~2s          |
| Math Agent Gen   | 1      | gemini-2.5-flash (code_exec)  | Content generation | ~30-60s      |
| Math Agent Parse | 2      | gemini-2.5-flash (structured) | Batch parse 7+6    | ~15-30s      |
| Reviewer         | 1      | gemini-3.1-flash-lite         | Batch review       | ~5-10s       |
| Formatter (quiz) | 2      | gemini-2.5-flash (structured) | Batch format 7+3   | ~10-20s      |
| **Total**        | **~7** |                               |                    | **~60-120s** |

With retry iterations: ×2-3 multiplier on worst cases.

---

## 2. Optimizations Implemented (2026-03-22)

### 2.1 Formatter Parallelization — `asyncio.gather()`

**Before:** Sequential `for game_type in request.game_types:` loop.
**After:** All game types formatted concurrently via `asyncio.gather()`.

```python
# Before: Sequential (~30-60s for 3 game types)
for game_type in request.game_types:
    if game_type == GameType.QUIZ:
        quiz_items = await _format_quizzes(reviewed_items, llm)
    elif game_type == GameType.FLASHCARD:
        flashcard_items = await _format_flashcards(reviewed_items, llm)
    ...

# After: Parallel (~10-20s for 3 game types)
results = await asyncio.gather(
    *[_safe_format(gt) for gt in request.game_types]
)
```

**Impact:** ~2-3× speedup for multi-game-type requests (most common case).

### 2.2 Batch Parse Retry with Backoff

**Before:** Single attempt per batch; failure = lost items, may trigger full retry iteration.
**After:** Up to 3 attempts per batch with linear backoff (1s, 2s).

**Impact:** Reduces full pipeline retry iterations (813s → ~200-300s estimated for "Số phức").

---

## 3. Proposed Optimizations (Not Yet Implemented)

### 3.1 Within-Pipeline Parallelization

#### A. Parallel Batch Parsing in Math Agent

Currently batches are parsed sequentially. Since each batch extracts different question ranges from the same raw text, they can run concurrently:

```python
# Current: Sequential
for batch_idx in range(num_batches):
    batch_result = await structured_llm.ainvoke(batch_messages)

# Proposed: Parallel
batch_tasks = [structured_llm.ainvoke(msg) for msg in all_batch_messages]
batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
```

**Impact:** ~2× speedup on parse phase (15-30s → 8-15s).
**Risk:** Higher burst rate on Vertex AI API. Monitor 429 rate-limit errors.

#### B. Parallel Batch Formatting Within Each Game Type

Each game type's formatter already batches by `FORMATTER_BATCH_SIZE=7`. These batches could also run in parallel:

```python
# Current: Sequential batches within _format_quizzes
for batch_start in range(0, len(items), FORMATTER_BATCH_SIZE):
    result = await chain.ainvoke(batch_data)

# Proposed: Parallel batches
batch_tasks = [chain.ainvoke(bd) for bd in all_batch_data]
results = await asyncio.gather(*batch_tasks, return_exceptions=True)
```

**Impact:** Additional ~1.5× for large question sets (20+ items).

### 3.2 Cross-Request Concurrency

#### Current Architecture

```
Client → POST /api/v1/generate → Firestore job → Cloud Tasks enqueue → Cloud Run HTTP
                                                                         ↓
Client ← GET  /api/v1/generations/{id} ← Firestore poll ← Pipeline execution (sequential)
```

Cloud Tasks already provides cross-request concurrency — each generation job is an independent HTTP request to Cloud Run.

#### A. Cloud Run Auto-Scaling

Cloud Run can scale to multiple instances. Each instance handles one pipeline run.

```yaml
# cloud-run-config
apiVersion: serving.knative.dev/v1
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/maxScale: "10" # Max 10 concurrent pipelines
        autoscaling.knative.dev/minScale: "0" # Scale to zero when idle
    spec:
      containerConcurrency: 1 # 1 pipeline per instance (CPU-bound on LLM I/O wait)
      timeoutSeconds: 600 # 10 min timeout per request
```

**Impact:** N concurrent users → N parallel pipeline runs (up to maxScale).
**Cost:** Pay-per-request. At 10 concurrent runs × $0.00002/vCPU-sec, ~$0.012/run.

#### B. Cloud Tasks Rate Limiting

Prevent burst overload on Vertex AI quotas:

```python
# Cloud Tasks queue config
queue_config = {
    "rate_limits": {
        "max_dispatches_per_second": 5,      # Max 5 new pipelines/sec
        "max_concurrent_dispatches": 10,     # Max 10 running simultaneously
    },
    "retry_config": {
        "max_attempts": 3,
        "min_backoff": "10s",
        "max_backoff": "300s",
    }
}
```

#### C. Vertex AI Quota Awareness

Gemini 2.5 Flash quota (asia-southeast1):

- Default: 60 RPM (requests per minute), 1M TPM (tokens per minute)
- Each pipeline run: ~7 LLM calls, ~3000 input tokens, ~5000 output tokens per call
- 10 concurrent runs: ~70 RPM, ~500K TPM → within default quota

**Recommendation:** Request quota increase to 200 RPM if expecting >15 concurrent users.

### 3.3 Request Batching (Future)

For use case: "teacher generates 100 questions for exam prep"

Instead of running 10 sequential pipeline invocations of 10Q each, split into parallel sub-jobs:

```
POST /api/v1/generate { num_questions: 100, ... }
  → Split into 10 sub-jobs of 10Q each
  → Enqueue all 10 to Cloud Tasks simultaneously
  → Each runs on separate Cloud Run instance
  → Aggregate results in Firestore
  → Return combined result

Timeline: 10 × ~120s sequential → ~120s parallel (10× speedup)
```

**Implementation:**

```python
# api/routes/generation.py
async def create_generation_job(request: GenerationRequest):
    if request.num_questions > 10:
        # Split into sub-jobs
        sub_size = 10
        sub_jobs = []
        for i in range(0, request.num_questions, sub_size):
            sub_req = request.copy()
            sub_req.num_questions = min(sub_size, request.num_questions - i)
            sub_job_id = await firestore.create_job(sub_req, parent_id=job_id)
            await task_queue.enqueue(sub_job_id)
            sub_jobs.append(sub_job_id)
        # Track parent job with sub-job references
        await firestore.update_job(job_id, sub_jobs=sub_jobs)
    else:
        await task_queue.enqueue(job_id)
```

**Complexity:** Medium. Needs parent/child job tracking in Firestore, result aggregation, partial failure handling.

### 3.4 Caching Layer (Future)

For repeated topic/difficulty combinations, cache pipeline results:

```python
# Cache key: hash(subject, topic, difficulty, num_questions, game_types)
cache_key = hashlib.sha256(f"{req.subject}:{req.topic}:{req.difficulty}:{req.num_questions}:{sorted(req.game_types)}".encode()).hexdigest()

# Check Firestore cache (TTL: 24h)
cached = await firestore.get_cache(cache_key)
if cached:
    return cached  # Skip entire pipeline
```

**Best for:** Same teacher generating similar content multiple times, or multiple teachers with same curriculum.

---

## 4. Priority Matrix

| Optimization                   | Effort       | Impact                 | Priority | Status      |
| ------------------------------ | ------------ | ---------------------- | -------- | ----------- |
| Formatter `asyncio.gather()`   | Low          | 2-3× formatter speed   | P0       | ✅ Done     |
| Batch parse retry              | Low          | Fewer full retries     | P0       | ✅ Done     |
| Cloud Run auto-scaling         | Low (config) | N concurrent users     | P1       | Not started |
| Cloud Tasks rate limiting      | Low (config) | Quota protection       | P1       | Not started |
| Parallel batch parsing         | Medium       | 2× parse speed         | P2       | Not started |
| Request batching (100Q→10×10Q) | Medium       | 10× for large requests | P2       | Not started |
| Parallel format batches        | Low          | 1.5× per game type     | P3       | Not started |
| Caching layer                  | Medium       | Skip pipeline entirely | P3       | Not started |

---

## 5. Estimated Performance After Optimizations

| Scenario                  | Current | With P0-P1       | With P0-P2      | With All      |
| ------------------------- | ------- | ---------------- | --------------- | ------------- |
| 1 user, 10Q, quiz-only    | ~120s   | ~100s            | ~80s            | ~80s          |
| 1 user, 10Q, 3 game types | ~180s   | ~120s            | ~100s           | ~100s         |
| 1 user, 100Q, quiz-only   | ~2000s  | ~1700s           | ~200s (batched) | ~200s         |
| 10 concurrent, 10Q each   | ~12000s | ~120s (parallel) | ~120s           | ~80s (cached) |
| 10 concurrent, 100Q each  | N/A     | ~2000s           | ~200s           | ~200s         |

**Key insight:** The biggest single improvement is **request batching** (P2) for large requests, and **Cloud Run auto-scaling** (P1) for concurrent users. These are independent and address different bottlenecks.

---

## 6. Implementation Roadmap

```
Phase 1 (Done): Formatter parallelization + batch parse retry
  ✅ asyncio.gather() in formatter_node
  ✅ Retry with backoff in math_agent batch parsing

Phase 2 (M4 - Deploy): Cloud Run config
  → Set containerConcurrency=1, maxScale=10
  → Configure Cloud Tasks rate limits
  → Monitor Vertex AI quota usage

Phase 3 (Post-M4): Request batching
  → Parent/child job model in Firestore
  → Split large requests into sub-jobs
  → Result aggregation endpoint

Phase 4 (Future): Advanced
  → Parallel batch parsing
  → Response caching
  → Quota-aware request scheduling
```
