# Pipeline 100% Delivery — Redesign Plan

> **Branch**: `fix/pipeline-100-percent-delivery`
> **Created**: 2026-03-30
> **Validated**: 2026-03-31 ✅
> **Goal**: ALL difficulty levels must deliver exactly `num_questions` items (100% delivery rate)

## Pre-Fix Results (Unacceptable)

| Difficulty | Pass Rate | Delivery | Verdict |
|---|---|---|---|
| recall | 100% | 10/10 | ✅ |
| comprehension | 89% | 8/10 | ❌ |
| application | 100% | 10/10 | ✅ |
| high_application | 60% | 3/10 | ❌ |

## Post-Fix Results (Validated 2026-03-29)

| Difficulty | Pass Rate | Delivery | Iterations | Time | Verdict |
|---|---|---|---|---|---|
| recall | 100% | 10/10 | 1 | 86s | ✅ |
| comprehension | 100% | 10/10 | 1 | 110s | ✅ |
| application | 90.9% | 10/10 | 3 | 332s | ✅ |
| high_application | 100% | 10/10 | 2 | 554s | ✅ |

> **🎉 ALL 4 DIFFICULTY LEVELS ACHIEVED 100% DELIVERY** (total 18 min)

## Root Cause Analysis — 6 Loss Points

### LP1: Review Router Threshold = 70% (CRITICAL)
- **File**: `reviewer.py` L232
- **Code**: `min_required = int(request.num_questions * 0.7)`
- **Impact**: Pipeline considers 7/10 "success" and proceeds to formatter
- **Fix**: Change to `min_required = request.num_questions`

### LP2: Max 3 Iterations Forces Acceptance (HIGH)
- **File**: `state.py` L60: `MAX_REVIEW_ITERATIONS = 3`
- **Impact**: After 3 feedback loops, pipeline accepts partial results
- **Fix**: Increase to 5 iterations

### LP3: No Escalating Overshoot on Retry (HIGH)
- **File**: `math_agent.py` L737-741
- **Impact**: Uses same overshoot ratio on each retry — if first attempt's overshoot was insufficient, retries won't help
- **Fix**: Multiply overshoot by `(1 + 0.3 * iteration_count)` on retries

### LP4: Overshoot Too Low for high_application (MEDIUM)
- **File**: `constants.py` L56: `"high_application": 2.0`
- **Impact**: 2.0x overshoot with 60% pass rate → 12/20 → enough for 10 but no margin
- **Fix**: Increase to 2.5x base overshoot

### LP5: Minimum Generation Floor Missing (MEDIUM)
- **File**: `math_agent.py` L741
- **Impact**: On retry with gap=2, generates `ceil(2 * 1.1) = 3` items — too few for reliable coverage
- **Fix**: Ensure `num_to_generate >= num_still_needed + 3`

### LP6: Parse/Format Losses (LOW)
- Already has retry + per-item fallback
- Low priority given other fixes are stronger

## Implementation Checklist (Verified 2026-03-31)

- [x] **C1**: `reviewer.py` — Change min_required to num_questions (100% threshold) ✅
- [x] **C2**: `state.py` — Increase MAX_REVIEW_ITERATIONS to 5 ✅
- [x] **C3**: `math_agent.py` — Add escalating overshoot multiplier on retries ✅
- [x] **C4**: `constants.py` — Increase high_application overshoot to 2.5 ✅
- [x] **C5**: `math_agent.py` — Add minimum generation floor (num_still_needed + 3) ✅
- [x] **C6**: Unit tests 47/47 passed + E2E validation 100% all 4 levels ✅

### Commits
- `315ea22` — fix: pipeline 100% delivery (C1–C5 + test fix)
- `3646ea0` — docs: timeline entry + validation script
