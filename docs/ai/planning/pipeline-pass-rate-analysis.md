# Pipeline Pass Rate Analysis & Improvement Plan

> **Date:** 2026-03-27  
> **Context:** Benchmark 13 test groups, 372 items, **84.6% avg pass rate**, 2189.1s  
> **Critical Issue:** `high_application` = 0% (gen=0, rejected=20), `medium_15q` = 57.7%

---

## 1. Benchmark Results Summary

| Test                  | Items | Pass Rate | Time (s) | Status |
| --------------------- | ----- | --------- | -------- | ------ |
| smoke_5q              | 5     | 100%      | 117.4    | ✅     |
| medium_15q            | 15    | 57.7%     | 186.5    | ⚠️     |
| large_30q             | 30    | 83.3%     | 193.4    | ⚠️     |
| multi_type            | 45    | 100%      | 78.6     | ✅     |
| broad_Hàm_số          | 40    | 100%      | 125.0    | ✅     |
| broad_Vectơ           | 30    | 68.2%     | 150.6    | ⚠️     |
| diff_recall           | 10    | 100%      | -        | ✅     |
| diff_comprehension    | 10    | 100%      | -        | ✅     |
| diff_application      | 10    | 90.9%     | -        | ✅     |
| diff_high_application | 0     | 0%        | 341.7    | ❌     |
| subj_Toán             | 60    | 100%      | -        | ✅     |
| subj_Lý               | 60    | 100%      | -        | ✅     |
| subj_Hóa              | 57    | 100%      | -        | ✅     |

---

## 2. Root Cause Analysis

### RC-1: Broken Feedback Loop (CRITICAL)

**Problem:** The graph has a feedback loop (reviewer → `"fail"` → supervisor → math_agent), but **the math_agent never receives the rejection reasons**.

**Evidence (code):**

- `reviewer_node()` writes `rejected_items` with `review_feedback` field to state
- `review_router()` returns `"fail"` when insufficient items, sending flow back to supervisor
- `math_agent_node()` only reads `state["request"]` and `state["doc_scope"]` — **never reads `state["rejected_items"]`**
- Result: On retry, math_agent blindly regenerates identical-quality items without knowing what went wrong

**Impact:** The entire feedback loop is architecturally present but functionally **inert**. Retries produce the same quality items, leading to the same rejections.

**Fix:** Pass `rejected_items` + `review_feedback` to math_agent prompt on retry iterations.

### RC-2: Generator-Reviewer Misalignment at `high_application` (CRITICAL)

**Problem:** 100% rejection rate (20/20 items rejected) at `high_application` difficulty.

**Evidence:**

- `MATH_AGENT_PROMPT` defines `high_application` as: "non-routine reasoning, synthesis, or modeling across concepts"
- `REVIEWER_PROMPT` checks: "high_application: Should require non-routine reasoning or cross-concept synthesis"
- Generation model (`gemini-2.5-flash`, temperature=0.7) produces standard textbook problems
- Review model (`gemini-3.1-flash-lite-preview`, temperature=0.0) correctly rejects them as not meeting cognitive level
- The generator lacks **exemplars** of what a genuine `high_application` question looks like

**Root cause:** The prompt describes `high_application` abstractly but provides **zero few-shot examples**. LLMs default to producing routine problems regardless of difficulty label. The reviewer is stricter than the generator's capability at this level.

### RC-3: Uniform Overshoot Ratio (MODERATE)

**Problem:** `YIELD_OVERSHOOT_RATIO = 1.3` (30% buffer) is applied uniformly across all difficulty levels.

**Evidence:**

- `recall`: 100% pass rate → 1.3x overshoot is wasteful
- `high_application`: 0% pass rate → even 10x overshoot wouldn't help (architectural issue)
- `medium_15q`: 57.7% → needs ~1.8x overshoot to hit 70% target

**Fix:** Adaptive overshoot by difficulty: `recall`=1.1, `comprehension`=1.2, `application`=1.4, `high_application`=2.0

### RC-4: Batch Parsing Item Loss (MODERATE)

**Problem:** Large requests split into batches (PARSE_BATCH_SIZE=7) where any batch failure = lost items.

**Evidence:**

- `medium_15q`: 15 requested × 1.3 = ~20 generated, split into 3 batches (7+7+6)
- If 1 batch fails parsing → lose ~7 items → can't meet 70% threshold
- `asyncio.gather()` runs all batches concurrently → rate limiter pressure

**Fix:** Sequential batch parsing with accumulation (don't gather all at once for large batches).

### RC-5: Review Threshold Not Difficulty-Aware (MINOR)

**Problem:** Fixed 0.7 review score threshold regardless of difficulty level.

**Evidence:**

- `high_application` questions are inherently harder to score well on "Educational Value" (20% weight)
- A question that's almost-but-not-quite high_application scores ~0.6 and gets rejected
- No gradual difficulty scaling in the scoring criteria

---

## 3. Solutions from Similar Systems

### 3.1 Quizizz AI Toolkit (Bloom's Taxonomy Generator)

- Uses **dedicated prompt templates per cognitive level**, not just a label in a single prompt
- `high_application` questions are generated with specific scaffolding: "provide a scenario that requires combining concepts X and Y"
- The UI shows examples for each Bloom's level to guide the AI

### 3.2 Higher Order Prompting (HOP) Model (Academic Research, 2025)

- Proposes adding a **"discovery" foundation level** before Bloom's levels
- Key insight: LLMs need **explicit structural patterns** for HOTS (Higher-Order Thinking Skills):
  - Application → "Given [scenario], apply [procedure] to solve [problem]"
  - Analysis → "Compare [X] vs [Y] using [criteria]"
  - Synthesis → "Design a [solution] that combines [concept A] and [concept B] under [constraint]"
- Recommended: 2-3 **few-shot exemplars per cognitive level** in the system prompt

### 3.3 Self-Improving Many-Shot Reasoners (OpenReview, 2025)

- Iteratively optimizes demonstrations based on what succeeds
- Key technique: **Select exemplars from previously successful generations** as few-shots
- Store pass-rate metadata per generated item → use highest-scoring items as future exemplars

### 3.4 SAGE Framework (Agentic Explainer, EACL 2026)

- Uses **Explainer LLM + Reviewer LLM** with **multi-turn refinement**
- Reviewer's feedback is **explicitly passed back** to the Explainer in next round
- Accept/Reject cycle with concrete feedback propagation (exactly what our pipeline is missing)

### 3.5 LangGraph Supervisor Pattern Best Practice (2026)

- Shared state should carry **action context** for retry loops
- Sub-agent wrappers should read `state["feedback"]` on iteration_count > 0
- Pattern: `if state["iteration_count"] > 0: inject rejected_items + feedback into prompt`

---

## 4. Recommended Action Plan

### P0: Fix Feedback Loop (most impact, moderate effort)

1. Modify `math_agent_node()` to read `state["rejected_items"]` when `iteration_count > 0`
2. Inject rejection feedback into the generation prompt: "Previously rejected items and reasons: ..."
3. Expected impact: Retry iterations will now improve quality instead of being wasted

### P1: Difficulty-Specific Few-Shot Exemplars (high impact, moderate effort)

1. Create exemplar bank: 2-3 gold-standard questions per difficulty level per subject
2. Store in `data/exemplars/{difficulty}/{subject}.json`
3. Inject matching exemplars into `MATH_AGENT_PROMPT` based on request difficulty
4. For `high_application`: provide explicit structural patterns (scenario-based, cross-concept synthesis)
5. Expected impact: `high_application` should go from 0% → 50%+ pass rate

### P2: Adaptive Overshoot Ratio (moderate impact, low effort)

1. Replace fixed `YIELD_OVERSHOOT_RATIO = 1.3` with difficulty-based mapping:
   ```python
   OVERSHOOT_BY_DIFFICULTY = {
       "recall": 1.1,
       "comprehension": 1.2,
       "application": 1.4,
       "high_application": 2.0,
   }
   ```
2. Expected impact: Better resource allocation, fewer wasted LLM calls for easy levels

### P3: Reviewer Difficulty Calibration (moderate impact, low effort)

1. Add difficulty-aware scoring guidance in `REVIEWER_PROMPT`:
   - `recall`/`comprehension`: strict on accuracy, lenient on cognitive level match
   - `high_application`: lenient on perfect cognitive match (accept "close to synthesis"), strict on accuracy
2. Adjust threshold: 0.7 for recall/comprehension, 0.6 for application, 0.55 for high_application
3. Expected impact: Reduce false-negative rejections at higher difficulty levels

### P4: Batch Parsing Reliability (low impact, low effort)

1. For batches > PARSE_BATCH_SIZE: use sequential parsing with jitter instead of concurrent gather
2. Add per-batch retry with fallback to single-item parsing on batch failure
3. Expected impact: Reduce item loss in medium/large requests

---

## 5. Priority Order

| Priority | Action                            | Expected Impact                            | Effort |
| -------- | --------------------------------- | ------------------------------------------ | ------ |
| P0       | Fix feedback loop                 | High — fixes the architectural flaw        | Medium |
| P1       | Few-shot exemplars per difficulty | High — directly addresses high_application | Medium |
| P2       | Adaptive overshoot                | Medium — better resource use               | Low    |
| P3       | Reviewer difficulty calibration   | Medium — reduces false rejections          | Low    |
| P4       | Batch parsing reliability         | Low — edge case improvement                | Low    |
