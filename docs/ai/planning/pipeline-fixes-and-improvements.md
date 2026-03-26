---
phase: planning
title: Pipeline Fixes & Improvements - Post-Testing
description: Ke hoach sua loi va cai thien pipeline sau test report 2026-03-21
priority: M3 (Quality & Tuning)
created: 2026-03-22
---

# Pipeline Fixes & Improvements

> **Tham chieu:** [Test Report 2026-03-21](../testing/pipeline-test-report-2026-03-21.md)
> **Trang thai:** ✅ M3 hoan thanh. Tat ca fixes/improvements da implement va regression test PASSED (2026-03-22).

---

## 0. Tong quan van de

Pipeline hien tai co 7 van de duoc phat hien tu 5 test cases (130 items, 923s).
Van de duoc chia thanh 3 nhom:

| Nhom                | Van de                                                           | Tac dong            |
| ------------------- | ---------------------------------------------------------------- | ------------------- |
| **Bug**             | reviewed_items bi ghi de moi iteration (P0)                      | Mat items da pass   |
| **Data Quality**    | dict[str,Any] chay khap pipeline, difficulty hardcode, 1:1 check | Loi ngam, kho debug |
| **Content Quality** | Reviewer khong on dinh, yield < 100%, difficulty khong phan hoa  | Chat luong noi dung |

---

## 1. Nghien cuu can thuc hien truoc khi code

### R1. Quy chuan dinh dang data trong LangGraph pipeline

**Van de hien tai:**

Content items chay qua pipeline duoi dang `list[dict]` - khong co type safety:

```
math_agent_node                     reviewer_node                     formatter_node
   GeneratedContentItem (Pydantic)     dict (json.dumps -> LLM)         dict -> QuizOutput (Pydantic)
   --> .model_dump() --> dict           --> dict + review_score          --> item.get("difficulty","medium")
                                        --> dict + review_feedback
```

- `math_agent` parse LLM output thanh `GeneratedContentItem` (Pydantic) nhung lap tuc convert sang dict (line 314-338 math_agent.py)
- `reviewer` nhan dict, them `review_score` va `review_feedback` bang dict mutation
- `formatter` doc dict bang `.get()` voi default values - neu key sai ten thi fail ngam
- Khong co validation giua cac node - item thieu field se chi loi o cuoi pipeline

**Can tim hieu:**

- [ ] **LangGraph state co ho tro Pydantic model truc tiep khong?** Hay phai dung TypedDict + dict?
  - Doc: https://langchain-ai.github.io/langgraph/concepts/low_level/#state
  - LangGraph `StateGraph` nhan TypedDict hoac Pydantic BaseModel lam schema
  - Nhung cac node return `dict` de merge vao state - day la convention cua LangGraph
  - **Ket luan:** Ca hai deu hoat dong. TypedDict + `Annotated[..., add]` la pattern pho bien nhat.

- [ ] **Cac pattern pho bien cho typed data flow trong LangGraph:**
  - Pattern 1: Giu dict nhung them validation function giua cac node
  - Pattern 2: Dung Pydantic model trong state (LangGraph ho tro tu v0.1+)
  - Pattern 3: Dung `ContentItem` (da co trong schemas) lam intermediate format
  - **Ket luan:** Chon Pattern 3 - giu TypedDict state, validate voi ContentItem tai math_agent, serialize bang model_dump(mode='json')

- [ ] **Review `ContentItem` schema hien co** (`src/api/schemas/game_content.py`):
  - Da co `ContentItem(BaseModel)` voi day du fields: question, answer, explanation, topic, difficulty, context_source, doc_scope, computation_trace
  - Hien tai KHONG duoc dung trong pipeline - chi la schema doc lap
  - **Ket luan:** Su dung ContentItem de validate, chuyen lai thanh dict cho state. Scalable - co the migrate sang full Pydantic state sau.

**Ket qua:** Chon Pattern 3 (TypedDict + ContentItem validation). Da implement 2026-03-22.

### R2. Phan hoa do kho trong giao duc Viet Nam

**Van de hien tai:**

Pipeline hardcode `difficulty = request.difficulty.value` cho tat ca items. Prompt chi noi "Questions should be at {difficulty} difficulty level" ma khong co tieu chi cu the.

**Can tim hieu:**

- [ ] **Khung phan hoa do kho theo Bloom's Taxonomy ap dung trong SGK Viet Nam:**
  - SGK 2018 (Chuong trinh Giao duc Pho thong moi) phan biet: Nhan biet - Thong hieu - Van dung - Van dung cao
  - Day la 4 muc do nhan thuc chinh thuc trong kiem tra danh gia tai VN
  - **Ket luan:** Doi sang 4 level: recall / comprehension / application / high_application

- [ ] **Tieu chi cu the cho moi mon STEM:**
  - recall: Nhan dien cong thuc, ghi nho dinh nghia, nhan biet khai niem
  - comprehension: Giai thich tai sao, dien giai bieu do, trinh bay y nghia
  - application: Giai bai toan nhieu buoc, ap dung quy trinh da hoc
  - high_application: Mo hinh hoa, tong hop nhieu kien thuc, bai toan phi thuong quy
  - **Ket luan:** Tieu chi da duoc tich hop vao prompt cua math_agent va reviewer

- [ ] **Tham khao tai lieu chinh thuc:**
  - Thong tu 22/2021/TT-BGDDT (Quy dinh danh gia hoc sinh THCS va THPT)
  - Ma tran de thi THPT quoc gia: Nhan biet 30-40% / Thong hieu 30% / Van dung 20-30% / Van dung cao 10%
  - **Ket luan:** Ty le chuan la khoang 40/30/20/10. Da luu vao DifficultyLevel docstring.

- [ ] **Quyet dinh DifficultyLevel enum:**
  - Chon Option B: 4 level voi tieng Anh values
  - `RECALL = "recall"`, `COMPREHENSION = "comprehension"`, `APPLICATION = "application"`, `HIGH_APPLICATION = "high_application"`
  - Breaking change: API v1.0.0 -> v1.1.0 (enum values thay doi)
  - **Ket luan:** Da implement. Default la COMPREHENSION.

**Ket qua:** 4-level DifficultyLevel voi English values. Da implement 2026-03-22.

---

## 2. Bug Fixes (lam truoc, khong can nghien cuu)

### F1. [P0] reviewed_items bi ghi de moi iteration

**File:** `src/graph/state.py` (1 dong)

**Hien tai:**

```python
reviewed_items: list[dict]                        # GHI DE moi iteration
rejected_items: Annotated[list[dict], add]        # TICH LUY
```

**Sua thanh:**

```python
reviewed_items: Annotated[list[dict], add]        # TICH LUY nhu rejected_items
rejected_items: Annotated[list[dict], add]        # TICH LUY
```

**Anh huong:** `review_router` da dung `len(reviewed_items)` - voi `add`, gia tri nay se phan anh tong tich luy. Khong can sua logic khac.

**Kiem tra:**

- [ ] Unit test: 2 iterations, iteration 1 pass 5 items, iteration 2 pass 3 items --> ket qua = 8 items
- [ ] E2E test: chay lai `test_pipeline_results.ipynb`, so sanh ket qua

**Trang thai:** [x] Hoan thanh 2026-03-22

### F2. [P2] Batch size hardcode --> constants

**File:** `src/graph/nodes/math_agent.py`, `src/graph/nodes/formatter.py`, `src/config/constants.py`

**Hien tai:**

```python
# math_agent.py line 263
PARSE_BATCH_SIZE = 7

# formatter.py line 79
FORMATTER_BATCH_SIZE = 7
```

**Sua thanh:**

```python
# constants.py - them:
PARSE_BATCH_SIZE: int = 7
FORMATTER_BATCH_SIZE: int = 7

# math_agent.py - thay:
from src.config.constants import PARSE_BATCH_SIZE

# formatter.py - thay:
from src.config.constants import FORMATTER_BATCH_SIZE
```

**Trang thai:** [x] Hoan thanh 2026-03-22

---

## 3. Cai thien Pipeline (lam sau R1, R2)

### I1. [P1] Typed data flow - thay dict bang Pydantic model

> **Phu thuoc:** R1 (nghien cuu pattern)

**Pham vi thay doi (du kien):**

| File              | Thay doi                                                                |
| ----------------- | ----------------------------------------------------------------------- |
| `state.py`        | `content_items: list[ContentItem]`, `reviewed_items: list[ContentItem]` |
| `math_agent.py`   | Bo doan convert dict, return `ContentItem` truc tiep                    |
| `reviewer.py`     | Nhan `ContentItem`, them `review_score` va `review_feedback` vao model  |
| `formatter.py`    | Doc tu `ContentItem` thay vi `dict.get()`                               |
| `game_content.py` | Them `review_score`, `review_feedback` vao `ContentItem` (optional)     |

**Rui ro:** LangGraph state serialization - can verify Pydantic model serialize/deserialize dung khi dung checkpointer (Firestore).

**Trang thai:** [x] Hoan thanh 2026-03-22. Giu TypedDict state, validate bang ContentItem.model_dump(mode='json') tai math_agent.

### I2. [P1] Difficulty phan hoa dua tren Bloom's Taxonomy VN

> **Phu thuoc:** R2 (nghien cuu quy chuan)

**Pham vi thay doi (du kien):**

| File              | Thay doi                                                           |
| ----------------- | ------------------------------------------------------------------ |
| `game_content.py` | Cap nhat `DifficultyLevel` enum (them level hoac giu 3 + metadata) |
| `math_agent.py`   | Them `difficulty` vao `GeneratedContentItem` schema                |
| `math_agent.py`   | Cap nhat prompt voi tieu chi difficulty cu the                     |
| `math_agent.py`   | Dung `item.difficulty` thay vi `request.difficulty.value`          |
| `reviewer.py`     | Them difficulty check vao reviewer prompt                          |
| `requests.py`     | Cap nhat `GenerationRequest` neu doi enum                          |

**Trang thai:** [x] Hoan thanh 2026-03-22. DifficultyLevel: 4 levels (recall/comprehension/application/high_application). Prompt math_agent + reviewer da cap nhat.

### I3. [P1] Reviewer prompt cai thien - on dinh hon

> **Khong can nghien cuu, co the lam song song voi R1/R2**

**Thay doi:**

1. **Them few-shot examples** vao `REVIEWER_PROMPT`:
   - 1 vi du PASS (score 0.9) - cau hoi toan tieng Viet chat luong
   - 1 vi du REJECT (score 0.4) - cau hoi lan tieng Anh hoac sai

2. **Vietnamese criteria cu the hon:**

   ```
   Vietnamese Quality (15%):
   - 0.0: Noi dung bang tieng Anh hoac lan lon
   - 0.5: Tieng Viet nhung khong tu nhien (dich may)
   - 0.8: Tieng Viet tu nhien, loi nho (sai thuat ngu chuyen mon)
   - 1.0: Tieng Viet chuan, dung thuat ngu hoc thuat
   ```

3. **Xem xet nang review model:**
   - Hien tai: `gemini-3.1-flash-lite-preview` (nho, re, khong on dinh)
   - Option: `gemini-2.5-flash` (lon hon, on dinh hon, chi phi tang ~3x)
   - Chi can doi env var `REVIEW_MODEL` - khong can sua code

**Trang thai:** [x] Hoan thanh 2026-03-22. Da cap nhat prompt voi difficulty-specific criteria va Vietnamese STEM terminology.

**Thay doi trong `math_agent_node`:**

```python
# Sinh thua 30% de bu cho items bi reject hoac LLM sinh thieu
num_to_generate = math.ceil(request.num_questions * YIELD_OVERSHOOT_RATIO)  # YIELD_OVERSHOOT_RATIO = 1.3
# Dung num_to_generate trong prompt thay vi request.num_questions
```

**Them trim logic trong `formatter_node`:**

```python
# Gioi han reviewed_items <= request.num_questions truoc khi format
if len(reviewed_items) > request.num_questions:
    reviewed_items = reviewed_items[:request.num_questions]
```

**Trang thai:** [x] Hoan thanh 2026-03-22. YIELD_OVERSHOOT_RATIO=1.3 trong constants.py.

### I5. [P2] Formatter 1:1 validation

**Them log warning khi so luong output != input trong moi batch format:**

```python
if len(result.questions) != len(batch_items):
    logger.warning(
        "formatter_count_mismatch",
        expected=len(batch_items),
        got=len(result.questions),
    )
```

Neu mismatch > 20%: retry batch do 1 lan.

**Trang thai:** [x] Hoan thanh 2026-03-22. Them logger.warning cho quiz/flashcard/fill_blank count mismatch.

---

## 4. Test cases can chay lai sau khi sua

| Test                | Muc dich                                   | Chay sau |
| ------------------- | ------------------------------------------ | -------- |
| reviewed_items_add  | Verify items tich luy qua iterations       | F1       |
| accuracy_10q        | Regression - ket qua khong te hon truoc    | F1, F2   |
| difficulty_mix      | Verify easy/medium/hard sinh dung          | I2       |
| vietnamese_improved | Verify reviewer on dinh hon (target > 80%) | I3       |
| scale_30q_yield     | Verify 30 yeu cau --> >= 28 output         | I4       |
| full_regression     | Chay lai 5 test goc, so sanh ket qua       | Tat ca   |

---

## 5. Thu tu thuc hien

```
Giai doan 1: Bug fixes (co the lam ngay)
  F1 --> F2 --> chay test regression

Giai doan 2: Nghien cuu (song song)
  R1 (data format) ---|
                      |--> Tong hop, quyet dinh approach
  R2 (difficulty VN) -|

Giai doan 3: Cai thien (sau nghien cuu)
  I3 (reviewer prompt) --> co the lam song song voi R1/R2
  I1 (typed data flow) --> phu thuoc R1
  I2 (difficulty)      --> phu thuoc R2
  I4 (yield)           --> doc lap
  I5 (formatter check) --> doc lap

Giai doan 4: Full regression test
  Chay lai 5 test goc + test moi
```

**Tien do:**

- [x] **Giai doan 1** - Bug fixes (F1, F2) -- Hoan thanh 2026-03-22
- [x] **Giai doan 2** - Nghien cuu (R1, R2) -- Hoan thanh 2026-03-22
- [x] **Giai doan 3** - Cai thien (I1-I5) -- Hoan thanh 2026-03-22
- [x] **Giai doan 4** - Full regression -- Hoan thanh 2026-03-22 (5/5 passed, 135 items, 93% pass rate, 900s)

---

## 6. Lien ket toi cac milestone chinh

Sau khi hoan thanh tat ca fixes/improvements o day, quay lai milestone chinh:

| Task chinh (tu planning goc) | Trang thai | Ghi chu                              |
| ---------------------------- | ---------- | ------------------------------------ |
| T4.2 Accuracy Testing        | ✅ Done    | 100/100 = 100% accuracy (2026-03-22) |
| T4.3 Performance Testing     | Chua lam   | Doc lap, co the lam song song        |
| T4.4 Deployment & IAM        | 50%        | Dockerfile done, can Cloud Run       |
| T4.5 E2E Testing             | Chua lam   | Can F1 fix truoc                     |
| T4.6 Documentation           | Chua lam   | Cap nhat sau khi code stable         |

---

## 7. Concurrency & Performance (2026-03-22)

### Implemented

- **Formatter parallelization:** `asyncio.gather()` for game types in `formatter_node` — ~2-3× speedup
- **Batch parse retry:** Up to 3 attempts with backoff in `math_agent` — fewer full retry iterations
- **Evaluator max_output_tokens fix:** 1024 → 4096 — resolved 26/100 eval errors

### Proposed (see `docs/ai/design/concurrency-and-performance-en.md`)

- **Cloud Run auto-scaling** (P1): containerConcurrency=1, maxScale=10
- **Cloud Tasks rate limiting** (P1): 5/s dispatch, 10 max concurrent
- **Request batching** (P2): 100Q → 10×10Q parallel sub-jobs (10× speedup)
- **Parallel batch parsing** (P2): `asyncio.gather()` for parse batches
- **Caching layer** (P3): skip pipeline for repeated topic/difficulty combos
