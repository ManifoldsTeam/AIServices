---
phase: implementation
title: Session Summary — Round 2 Model Upgrade & Pipeline Optimization
date: 2026-03-29
branch: feat/mvp
---

# Session Summary: 2026-03-29 — Round 2 Model Upgrade & Pipeline Optimization

## Phạm vi Session

Nâng cấp model Gemini để tăng reasoning capability, tối ưu pipeline cho high_application difficulty level, sửa formatter item drop bug.

---

## Những gì đã làm

### 1. Model Upgrade

| Setting                     | Trước                           | Sau                      |
| --------------------------- | ------------------------------- | ------------------------ |
| `GENERATION_MODEL`          | `gemini-2.5-flash`              | `gemini-3-flash-preview` |
| `REVIEW_MODEL`              | `gemini-3.1-flash-lite-preview` | `gemini-3-flash-preview` |
| `GENERATION_MODEL_LOCATION` | `asia-southeast1`               | `global`                 |
| `REVIEW_MODEL_LOCATION`     | `global`                        | `global`                 |

**QUAN TRỌNG:** `gemini-3-flash-preview` CHỈ available ở endpoint `global`, KHÔNG có ở `asia-southeast1` (sẽ trả về 404 NOT_FOUND).

### 2. Enriched High Application Exemplars (`math_agent.py`)

- Thêm exemplar cho chemistry (4), physics (2), biology (1)
- Thêm `HIGH_APPLICATION_ANTI_PATTERNS` — 4 common mistakes cần tránh
- Thêm biology subject detection trong `_infer_subject()` (kiểm tra biology TRƯỚC physics để tránh collision "quang hợp")

### 3. Reject Feedback Classification System (`math_agent.py`)

- `_ERROR_PATTERNS`: list (category, regex) cho cognitive_level, accuracy, clarity, domain
- `_ERROR_GUIDANCE`: dict mapping category → targeted fix instructions
- `_classify_feedback()`: phân loại rejection feedback thành error category
- `_build_rejection_feedback()`: thêm `[category]` labels và `TARGETED FIX GUIDANCE` section
- Accuracy regex: `accura|incorrect|sai|wrong|error|lỗi|tính toán|calculation|formula|công thức|inconsistent|mismatch|không khớp|math`

### 4. Formatter Retry Fix (`formatter.py`)

**Vấn đề:** Batch structured output parsing failed silently → drop 30-60% items.

**Giải pháp:** `_invoke_batch_with_retry()` helper:

1. Thử batch `_FORMAT_MAX_RETRIES=2` lần
2. Nếu batch vẫn fail → fallback format từng item riêng lẻ
3. Áp dụng cho `_format_quizzes()`, `_format_flashcards()`, `_format_fill_blanks()`

**Kết quả:** 0% formatter drop (trước đó 30-60%).

### 5. Test Updates

- 84 tests pass (unit + integration + system)
- Updated test fixtures: model name, location, difficulty levels
- 14 new unit tests: TestFeedbackClassification (7), TestSubjectInference (4), TestAntiPatterns (3)

---

## Kết quả Benchmark

### Round 2d: All Difficulty Levels (topic: Phản ứng oxi hóa khử, 10 quiz)

| Difficulty       | Pass Rate | Delivery | Generated | Passed | Rejected | Iterations | Time   |
| ---------------- | --------- | -------- | --------- | ------ | -------- | ---------- | ------ |
| recall           | 100.0%    | 10/10    | 10        | 10     | 0        | 1          | 84.6s  |
| comprehension    | 88.9%     | 8/10     | 9         | 8      | 1        | 1          | 149.7s |
| application      | 100.0%    | 10/10    | 10        | 10     | 0        | 2          | 233.5s |
| high_application | 60.0%     | 3/10     | 5         | 3      | 2        | 3          | 584.3s |

**Overall: avg_pass_rate=87.2%, avg_delivery=78%**

### So sánh với Round 1 Baseline (high_application)

| Metric           | Round 1 (gemini-2.5-flash) | Round 2c (best) | Round 2d |
| ---------------- | -------------------------- | --------------- | -------- |
| Review pass rate | ~10%                       | 83.3%           | 60.0%    |
| Delivery         | 0-1/10                     | 10/10           | 3/10     |
| Formatter drops  | 30-60%                     | 0%              | 0%       |

### Phân tích

- **Model upgrade là lever chính** (+73pp review pass rate cho high_application)
- **recall & application**: hoàn hảo (100% pass, 100% delivery)
- **comprehension**: tốt (89% pass, 80% delivery)
- **high_application**: cải thiện lớn nhưng variance cao (60-83% pass, 30-100% delivery)
- **Formatter retry**: loại bỏ hoàn toàn item loss (trước 30-60%)

---

## Vấn đề Tồn đọng

| Vấn đề                                            | Mức độ | Ghi chú                                                               |
| ------------------------------------------------- | ------ | --------------------------------------------------------------------- |
| high_application variance cao                     | P1     | 60-83% pass rate, delivery 30-100%. Cần thêm iteration hoặc overshoot |
| comprehension delivery 8/10                       | P2     | Pipeline dừng sau 1 iteration dù chưa đủ 10 items                     |
| Pipeline retry dựa trên pass rate, không quantity | P2     | Cần thêm logic kiểm tra số lượng items đủ chưa                        |

---

## Files Đã Thay Đổi

| File                                                    | Thay đổi                                          |
| ------------------------------------------------------- | ------------------------------------------------- |
| `.env.develop`                                          | Model names + locations                           |
| `src/graph/nodes/math_agent.py`                         | Exemplars, anti-patterns, feedback classification |
| `src/graph/nodes/formatter.py`                          | `_invoke_batch_with_retry()` + retry logic        |
| `src/config/settings.py`                                | Model upgrade comment                             |
| `tests/conftest.py`                                     | Model fixtures                                    |
| `tests/unit/test_llm_service.py`                        | Model assertions                                  |
| `tests/unit/test_pipeline_fixes.py`                     | 14 new tests                                      |
| `tests/integration/test_singleton_cache_integration.py` | Model assertions                                  |
| `tests/test_pipeline_core.py`                           | Difficulty level fixes                            |
| `tests/test_accuracy_scale.py`                          | Difficulty default                                |
| `notebooks/tests/test_graph_pipeline.ipynb`             | Round 2 test cells                                |

---

## Thông tin Kỹ thuật

### Model Availability

- `gemini-3-flash-preview`: CHỈ `global` endpoint. KHÔNG available ở `asia-southeast1`.
- `gemini-3.1-flash-lite-preview`: available ở `global`.
- `gemini-2.5-flash`: available ở `asia-southeast1`.

### Formatter Constants

- `FORMATTER_BATCH_SIZE = 7`
- `_FORMAT_MAX_RETRIES = 2`
- `STRUCTURED_MAX_TOKENS = 8192`

### Pipeline Constants

- `MAX_REVIEW_ITERATIONS = 3`
- `REVIEW_THRESHOLD_BY_DIFFICULTY`: controls when pipeline stops retrying
- `OVERSHOOT_BY_DIFFICULTY`: controls generation count multiplier

---

## TODO Tiếp Theo

1. **Giảm variance high_application** — tăng overshoot ratio hoặc thêm logic retry khi delivery < requested
2. **Sửa comprehension delivery** — pipeline nên retry khi số lượng items chưa đủ
3. **Multi-topic test** — test với nhiều chủ đề khác nhau (không chỉ hóa học)
4. **Notebook cleanup** — xóa debug cells (34-38) từ 404 investigation
