---
phase: design
title: Concurrency & Performance Optimization (v2)
description: Architecture for handling concurrent requests and reducing per-request latency
created: 2026-03-22
updated: 2026-03-24
status: Updated Proposal — Research-backed
research_sources: Tavily Pro research (2026-03-24), Vertex AI docs, LangGraph docs, asyncio best practices
---

# Concurrency & Performance Optimization (v2)

> **Updated:** 2026-03-24
> **Research:** Tavily Pro deep research on LLM pipeline concurrency patterns (33 sources)
> **Scope:** Within-pipeline parallelism, cross-request scaling, rate limiting, batch processing

---

## 1. Current Performance Baseline (Post-M3 Optimizations)

### Pipeline Test Results (M3 accuracy test — 368 items)

| Test                  | Items | Pass%   | Time    | Notes                                |
| --------------------- | ----- | ------- | ------- | ------------------------------------ |
| smoke_5q              | 5     | 100%    | 64.2s   |                                      |
| medium_15q            | 15    | 100%    | 92.8s   |                                      |
| large_30q             | 25    | 64.1%   | 125.0s  | **429 rate limit errors observed**   |
| multi_type (3 games)  | 45    | 100%    | 70.9s   | Formatter parallelization working    |
| diff_application      | 7     | 100%    | 163.5s  |                                      |
| diff_high_application | 1     | 7.1%    | 434.9s  | Broken — KB lacks exercise exemplars |
| **TOTAL**             | 368   | **89%** | 1700.2s | 28.3min for full suite               |

### LLM Call Chain Per Pipeline Run (10Q quiz-only)

| Node             | Calls  | Model                         | Purpose            | Est. Time    |
| ---------------- | ------ | ----------------------------- | ------------------ | ------------ |
| Supervisor       | 1      | gemini-3.1-flash-lite         | Classification     | ~2s          |
| Math Agent Gen   | 1      | gemini-2.5-flash (code_exec)  | Content generation | ~30-60s      |
| Math Agent Parse | 1-2    | gemini-2.5-flash (structured) | Batch parse 7+6    | ~15-30s      |
| Reviewer         | 1      | gemini-3.1-flash-lite         | Batch review       | ~5-10s       |
| Formatter (quiz) | 1-2    | gemini-2.5-flash (structured) | Batch format 7+3   | ~10-20s      |
| **Total**        | **~7** |                               |                    | **~60-120s** |

With retry iterations: ×2-3 multiplier on worst cases.

### Key Problem: No Rate Limiting on LLM Calls

**429 errors in `large_30q` test** — parallel batch parsing fires 4+ concurrent LLM calls without any rate control. With 60 RPM default quota (asia-southeast1), burst patterns exceed limits.

---

## 2. Optimizations Implemented (M3 — Done)

| Optimization                                  | Where                                     | Impact                                        |
| --------------------------------------------- | ----------------------------------------- | --------------------------------------------- |
| Formatter `asyncio.gather()` for game types   | `formatter.py`                            | 2-3× speedup for multi-game requests          |
| Batch parse retry with backoff                | `math_agent.py` `_parse_batch()`          | Fewer full pipeline retries                   |
| Parallel batch parsing via `asyncio.gather()` | `math_agent.py` `_parse_raw_content()`    | 2× parse speed                                |
| Code trace truncation (8000 chars)            | `math_agent.py` `_truncate_code_traces()` | Better parse success rate                     |
| Internal generation retry (2 attempts)        | `math_agent.py` `math_agent_node()`       | Avoids full pipeline restart on parse failure |
| Early termination on empty output             | `math_agent.py`                           | Skip useless parse attempts                   |

---

## 3. Proposed Architecture: Layered Concurrency Control

Based on research of production LLM systems, Vertex AI best practices, and asyncio patterns.

### 3.1 Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Layer 1: API Gateway                          │
│   POST /api/v1/generate → Firestore job → queue dispatch            │
│   Request splitting: 100Q → 10×10Q sub-jobs                         │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│                  Layer 2: Job Scheduler                               │
│   Cloud Tasks queue (rate: 5/s, max concurrent: 10)                  │
│   OR local asyncio.Queue with worker pool (dev mode)                 │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│               Layer 3: Per-Instance Rate Limiter                     │
│   AsyncTokenBucket (capacity=5, refill=1.0/s per 60RPM)             │
│   + asyncio.Semaphore(10) per-process concurrency cap                │
│   Every LLM call → bucket.wait_and_consume() → sema acquire         │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│             Layer 4: LangGraph Pipeline Execution                    │
│   supervisor → math_agent → reviewer → formatter → END              │
│   Internal: parallel batch parse, parallel game-type format          │
│   Per-node retry with backoff (not full graph retry)                 │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│            Layer 5: Circuit Breaker + Observability                   │
│   Trip after 5 consecutive 429s → cooldown 60s                      │
│   Metrics: latency p95, 429 rate, queue depth, bucket fill level    │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Layer 3 Detail: AsyncTokenBucket + Semaphore

**Purpose:** Prevent 429 errors by pacing LLM calls client-side to match Vertex AI quotas.

```python
# src/services/rate_limiter.py

import asyncio
import time
from dataclasses import dataclass, field

@dataclass
class AsyncTokenBucket:
    """Async-safe token bucket for rate limiting LLM calls.

    capacity: max burst size (requests)
    refill_rate: tokens/second (e.g., 1.0 for 60 RPM)
    """
    capacity: float
    refill_rate: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(init=False)

    def __post_init__(self):
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    async def wait_and_consume(self, amount: float = 1.0):
        """Block until a token is available, then consume it."""
        while True:
            async with self._lock:
                await self._refill()
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                needed = amount - self._tokens
                wait_time = needed / self.refill_rate if self.refill_rate > 0 else 1.0
            await asyncio.sleep(wait_time)


# Module-level singleton (created once per process)
# 60 RPM = 1 req/sec average, allow burst of 5
_llm_bucket = AsyncTokenBucket(capacity=5.0, refill_rate=1.0)
_llm_semaphore = asyncio.Semaphore(10)  # max 10 concurrent LLM calls

async def rate_limited_llm_call(coro):
    """Wrap any LLM call with rate limiting + concurrency cap.

    Usage:
        result = await rate_limited_llm_call(llm.ainvoke(messages))
    """
    await _llm_bucket.wait_and_consume()
    async with _llm_semaphore:
        return await coro
```

**Why this design:**

- **Token bucket** enforces average rate (1 req/s = 60 RPM) while allowing short bursts (capacity=5)
- **Semaphore** caps concurrent HTTP connections to prevent resource exhaustion
- **Module-level singletons** ensure all pipeline nodes share the same limiter
- No external dependencies (Redis not needed for single-instance local/Cloud Run)

**Tuning for quota:**

| Quota (RPM)     | `refill_rate` | `capacity` | `semaphore` | Max Concurrent Instances |
| --------------- | ------------- | ---------- | ----------- | ------------------------ |
| 60 (default)    | 1.0           | 5          | 10          | 1 (safety margin)        |
| 200 (requested) | 3.0           | 10         | 15          | 3-5                      |
| 500 (high)      | 8.0           | 15         | 20          | 8-10                     |

### 3.3 Integration Points in Current Codebase

Where to wire `rate_limited_llm_call()`:

| File            | Function                | LLM Calls                  | Change                 |
| --------------- | ----------------------- | -------------------------- | ---------------------- |
| `math_agent.py` | `math_agent_node()`     | `code_exec_llm.ainvoke()`  | Wrap with rate limiter |
| `math_agent.py` | `_parse_batch()`        | `structured_llm.ainvoke()` | Wrap with rate limiter |
| `formatter.py`  | `_format_quizzes()`     | `chain.ainvoke()`          | Wrap with rate limiter |
| `formatter.py`  | `_format_flashcards()`  | `chain.ainvoke()`          | Wrap with rate limiter |
| `formatter.py`  | `_format_fill_blanks()` | `chain.ainvoke()`          | Wrap with rate limiter |
| `reviewer.py`   | `reviewer_node()`       | `review_llm.ainvoke()`     | Wrap with rate limiter |
| `supervisor.py` | `supervisor_node()`     | `llm.ainvoke()`            | Wrap with rate limiter |

**Minimal code change per call site:**

```python
# Before:
result = await structured_llm.ainvoke(messages)

# After:
from src.services.rate_limiter import rate_limited_llm_call
result = await rate_limited_llm_call(structured_llm.ainvoke(messages))
```

### 3.4 Layer 5 Detail: Circuit Breaker

**Purpose:** Stop retrying when the provider is persistently failing (quota exhausted, outage).

```python
# Add to src/services/rate_limiter.py

@dataclass
class CircuitBreaker:
    """Simple circuit breaker for LLM provider failures."""
    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    _consecutive_failures: int = field(init=False, default=0)
    _tripped_at: float | None = field(init=False, default=None)

    def record_success(self):
        self._consecutive_failures = 0
        self._tripped_at = None

    def record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._tripped_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        if self._tripped_at is None:
            return False
        elapsed = time.monotonic() - self._tripped_at
        if elapsed > self.cooldown_seconds:
            # Half-open: allow one attempt
            self._tripped_at = None
            self._consecutive_failures = 0
            return False
        return True
```

---

## 4. Proposed Optimizations: Prioritized Implementation

### P0 — Within-Pipeline Parallelism (DONE)

| Optimization                                  | Status | File            |
| --------------------------------------------- | ------ | --------------- |
| Formatter `asyncio.gather()` for game types   | Done   | `formatter.py`  |
| Batch parse retry with backoff                | Done   | `math_agent.py` |
| Parallel batch parsing via `asyncio.gather()` | Done   | `math_agent.py` |
| Code trace truncation (8000 chars)            | Done   | `math_agent.py` |
| Internal generation retry (2 attempts)        | Done   | `math_agent.py` |

### P1 — Client-Side Rate Limiting (CRITICAL — Blocks all scaling)

**Problem:** 429 errors in `large_30q` test. No rate control on any LLM call.

**Solution:** `AsyncTokenBucket` + `asyncio.Semaphore` (Section 3.2 above)

**Implementation steps:**

1. Create `src/services/rate_limiter.py` with `AsyncTokenBucket`, `CircuitBreaker`, and `rate_limited_llm_call()`
2. Wire into all 7 LLM call sites (table in Section 3.3)
3. Add rate limiter config to `Settings` (env-configurable: `LLM_RATE_LIMIT_RPM`, `LLM_MAX_CONCURRENT`)
4. Test with `large_30q` — expect 429 errors to disappear

**Effort:** Low-Medium (1 new file + 7 one-line wrappers)
**Impact:** Eliminates 429 errors, enables safe parallel operations, prerequisite for all scaling

### P2 — Parallel Format Batches Within Game Types

**Problem:** Each game type's formatter runs batches sequentially inside `_format_quizzes()`, `_format_flashcards()`, `_format_fill_blanks()`.

**Current pattern:**

```python
for batch_start in range(0, len(items), FORMATTER_BATCH_SIZE):
    result = await chain.ainvoke(...)  # Sequential!
```

**Proposed pattern:**

```python
batch_tasks = [chain.ainvoke(bd) for bd in all_batch_data]
results = await asyncio.gather(*batch_tasks, return_exceptions=True)
```

**Prerequisite:** P1 rate limiter (prevents burst overload)
**Impact:** ~1.5× for large sets (20+ items per game type)
**Effort:** Low (refactor 3 formatter functions)

### P3 — Request Batching (100Q → N×10Q Sub-Jobs)

**Use case:** Teacher generates 100 questions for exam prep.

**Architecture:**

```
POST /generate { num_questions: 100 }
  │
  ├─ Split: 10 sub-jobs × 10Q each
  │    ├─ sub-1: { num_questions: 10, topic: same, offset: 0 }
  │    ├─ sub-2: { num_questions: 10, topic: same, offset: 10 }
  │    └─ ...
  │
  ├─ Schedule: asyncio.Queue(maxsize=20) + N workers
  │    ├─ Worker 1: run_pipeline(sub-1) → checkpoint result
  │    ├─ Worker 2: run_pipeline(sub-2) → checkpoint result
  │    └─ ... (bounded by rate limiter)
  │
  └─ Aggregate: collect results → order by offset → merge → return
```

**Implementation pattern (local async mode):**

```python
import asyncio
import itertools

def chunkify(items, chunk_size):
    it = iter(items)
    while True:
        chunk = list(itertools.islice(it, chunk_size))
        if not chunk:
            break
        yield chunk

async def batch_generate(request, max_workers=5):
    """Split large request into sub-jobs, process with bounded parallelism."""
    if request.num_questions <= 10:
        return await run_pipeline(request)

    chunks = list(range(0, request.num_questions, 10))
    queue = asyncio.Queue(maxsize=max_workers * 2)
    results = {}

    async def worker(worker_id):
        while True:
            try:
                offset = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            sub_req = request.model_copy()
            sub_req.num_questions = min(10, request.num_questions - offset)
            result = await run_pipeline(sub_req)
            results[offset] = result
            queue.task_done()

    for offset in chunks:
        await queue.put(offset)

    workers = [asyncio.create_task(worker(i)) for i in range(max_workers)]
    await queue.join()
    for w in workers:
        w.cancel()

    # Merge ordered
    return merge_results(sorted(results.items()))
```

**For Cloud Tasks mode:** Each sub-job = separate Cloud Tasks entry → separate Cloud Run instance.

**Partial failure handling:**

- Each sub-job checkpoints independently (Firestore status per sub-job)
- Failed sub-jobs can be retried individually
- Parent job aggregates: if >=80% sub-jobs succeed, return partial result + failure report

**Impact:** 10× speedup for 100Q (2000s → ~200s)
**Effort:** Medium
**Prerequisite:** P1 rate limiter

### P4 — Cross-Instance Rate Limiting (Production Multi-Instance)

**When needed:** Multiple Cloud Run instances sharing the same Vertex AI project quota.

**Options (increasing complexity):**

| Approach                        | When          | Complexity           | Recommendation                  |
| ------------------------------- | ------------- | -------------------- | ------------------------------- |
| Per-instance token bucket       | <=3 instances | None (already in P1) | Divide quota by max instances   |
| Cloud Tasks dispatch rate       | Any scale     | Low (config)         | Set `max_dispatches_per_second` |
| Redis-backed distributed bucket | >5 instances  | Medium               | Use `self-limiters` library     |

**For our scale (<=10 instances):** Cloud Tasks rate limiting (5/s dispatch, 10 max concurrent) is sufficient. No Redis needed until >50 RPM per instance.

### P5 — Caching Layer (Future)

**Strategy:** Cache at two levels:

1. **Vertex AI Search results** — same query+topic+scope → same context (TTL: 1h)
2. **Pipeline output** — same request params → same content (TTL: 24h, with randomization)

```python
# Cache key includes all params that affect output
cache_key = f"{subject}:{topic}:{difficulty}:{num_questions}:{sorted(game_types)}"
cache_hash = hashlib.sha256(cache_key.encode()).hexdigest()
```

**Impact:** Skip entire pipeline for repeated requests
**When:** After user patterns are known from production usage data

---

## 5. Priority Matrix (Updated)

| #     | Optimization                     | Effort       | Impact                    | Priority | Status       | Depends On      |
| ----- | -------------------------------- | ------------ | ------------------------- | -------- | ------------ | --------------- |
| 1     | Formatter `asyncio.gather()`     | Low          | 2-3× formatter            | P0       | Done         | —               |
| 2     | Batch parse retry + backoff      | Low          | Fewer retries             | P0       | Done         | —               |
| 3     | Parallel batch parsing           | Low          | 2× parse speed            | P0       | Done         | —               |
| 4     | Code trace truncation            | Low          | Better parse rate         | P0       | Done         | —               |
| 5     | Internal gen retry               | Low          | No pipeline restart       | P0       | Done         | —               |
| **6** | **AsyncTokenBucket + Semaphore** | **Low-Med**  | **Eliminates 429s**       | **P1**   | **Next**     | —               |
| **7** | **Circuit breaker**              | **Low**      | **Prevents retry storms** | **P1**   | **Next**     | #6              |
| 8     | Parallel format batches          | Low          | 1.5× per game type        | P2       | Not started  | #6              |
| 9     | Request batching (100Q→10×10Q)   | Medium       | 10× large requests        | P3       | Not started  | #6              |
| 10    | Cloud Tasks rate limiting        | Low (config) | Quota protection          | P4       | Deploy phase | —               |
| 11    | Cloud Run auto-scaling           | Low (config) | N concurrent users        | P4       | Deploy phase | #10             |
| 12    | Caching layer                    | Medium       | Skip pipeline             | P5       | Future       | Production data |

---

## 6. Estimated Performance After Optimizations

| Scenario             | Current (M3)         | +P1 (rate limit)      | +P2 (parallel fmt) | +P3 (batching) | +P4/P5 (deploy)    |
| -------------------- | -------------------- | --------------------- | ------------------ | -------------- | ------------------ |
| 1 user, 10Q, quiz    | ~90s                 | ~90s                  | ~80s               | ~80s           | ~80s               |
| 1 user, 10Q, 3 games | ~70s                 | ~70s                  | ~60s               | ~60s           | ~60s               |
| 1 user, 30Q, quiz    | ~125s (**64% pass**) | ~140s (**~95% pass**) | ~120s              | ~120s          | ~120s              |
| 1 user, 100Q, quiz   | ~2000s               | ~2000s                | ~1800s             | **~200s**      | ~200s              |
| 10 concurrent, 10Q   | Sequential           | Sequential            | Sequential         | Sequential     | **~120s parallel** |

**Key insights:**

1. **P1 (rate limiter) is the #1 priority** — fixes the 429 reliability issue in `large_30q` (64% → ~95% pass rate)
2. **P3 (request batching) gives the biggest latency win** for large requests (10× speedup)
3. **P4 (Cloud Run/Tasks) enables multi-user concurrency** — deferred to deploy phase as per user request

---

## 7. Implementation Roadmap

```
Phase 1 (M3 — Done): Within-pipeline parallelism
  ✅ asyncio.gather() in formatter_node (game types parallel)
  ✅ asyncio.gather() in _parse_raw_content (batch parsing parallel)
  ✅ Retry with backoff in _parse_batch, math_agent_node
  ✅ Code trace truncation, early termination

Phase 2 (Next Sprint): Client-side rate limiting
  → Create src/services/rate_limiter.py (AsyncTokenBucket + CircuitBreaker)
  → Wire rate_limited_llm_call() into all 7 LLM call sites
  → Add LLM_RATE_LIMIT_RPM and LLM_MAX_CONCURRENT to Settings
  → Test: large_30q should pass >90% (currently 64%)
  → Parallel format batches in formatter (after rate limiter is stable)

Phase 3 (Future Sprint): Request batching
  → Parent/child job model (Firestore or local)
  → asyncio.Queue + worker pool for local mode
  → Split 100Q → 10×10Q with bounded parallelism
  → Partial failure handling + result aggregation

Phase 4 (Deploy Phase — deferred):
  → Cloud Run auto-scaling (containerConcurrency=1, maxScale=10)
  → Cloud Tasks rate limiting (5/s dispatch, 10 concurrent)
  → Distributed rate limiter (only if >5 instances needed)
  → Caching layer (after production usage patterns observed)
```

---

## 8. Vertex AI Quota Reference

| Dimension | Default (asia-southeast1) | Our Usage (1 pipeline) | 10 Concurrent       | Action Needed                             |
| --------- | ------------------------- | ---------------------- | ------------------- | ----------------------------------------- |
| RPM       | 60                        | ~7                     | ~70                 | Request increase to 200 if >15 concurrent |
| TPM       | 1,000,000                 | ~56,000                | ~560,000            | Within limits                             |
| RPD       | 1,500                     | ~7                     | ~700/day (100 runs) | Within limits                             |

**Recommendation:** For production, request quota increase to 200 RPM. With the token bucket rate limiter, even the default 60 RPM will work for <=8 concurrent pipelines.

---

## Appendix A: Research Sources

This design was informed by:

- Vertex AI retry strategy docs (exponential backoff + jitter for 429/5xx)
- Gemini API rate limits docs (multi-dimensional: RPM, TPM, RPD per project)
- Published async token-bucket implementations for Python/asyncio
- LangGraph superstep execution model (fan-out via Send/Command, per-node retries)
- `asynciolimiter` and `self-limiters` libraries for async rate limiting
- `tenacity` for async retry with backoff integration
- AWS/Redis patterns for distributed rate limiting (token bucket + sliding window)
- LLM load testing best practices (k6 ramp/spike/soak profiles)
- Portkey.ai circuit breaker patterns for LLM applications
