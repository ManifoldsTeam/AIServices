# Project Timeline

> Nhật ký phát triển theo thời gian — mỗi entry ghi lại **vấn đề, nguyên nhân, hành động, và kết quả**.  
> Agent PHẢI tự động thêm entry mới sau mỗi lần triển khai thay đổi đáng kể.

---

## Format

```
### YYYY-MM-DD — [Tiêu đề ngắn gọn]

**Vấn đề:** Mô tả bug/yêu cầu gốc
**Nguyên nhân:** Phân tích root cause
**Hành động:** Các bước xử lý chính
**Kết quả:** Trạng thái sau khi xử lý

**References:**
- [file-path](file-path) — mô tả thay đổi
```

---

## Entries

### 2026-03-26 — Refactor bucket structure & bổ sung 798 PDFs (SGK + SBT)

**Vấn đề:** Pipeline sinh đề thi fail hàng loạt do timeout. Agent trong graph phải tự sinh câu hỏi dạng vận dụng trở lên vì thiếu dữ liệu bài tập (SBT) trong bucket — chỉ có 226 file SGK cũ với path structure không nhất quán (`system/sgk/lop-10/...` vs code dùng `system/{date}/{session_id}/...`).

**Nguyên nhân:**

1. Bucket chỉ chứa SGK (~226 file), không có SBT/bài tập → LLM phải tự generate toàn bộ câu hỏi vận dụng → vượt timeout
2. Path structure giữa code (`document_store.py`) và notebook (`manage_bucket_data.ipynb`) xung đột → khó quản lý batch upload vs API upload
3. Metadata thiếu trường `doc_type` để phân biệt SGK/SBT

**Hành động:**

1. Download 556 file SBT mới từ loigiaihay.com (tổng cộng 798 PDF: 226 SGK + 556 SBT + 16 khác)
2. Thống nhất path structure: `system/{grade}/{doc_type}/{subject}/{filename}` (Decision D1=Option A)
3. Refactor `document_store.py`: cập nhật `build_gcs_path()` và `upload_document()` hỗ trợ `grade`, `doc_type`, `subject`
4. Thêm `DOC_TYPES` vào `constants.py`
5. Metadata GCS: thêm trường `doc_type` (Decision D2=Yes)
6. Giữ nguyên admin API — không thêm `doc_type` param (Decision D3=No), sử dụng date-based fallback
7. Xóa 226 file cũ → upload 798 file mới → trigger Vertex AI Search FULL re-import
8. Rewrite notebook loại bỏ toàn bộ hardcoded vars, dùng `get_settings()`

**Kết quả:**

- ✅ 798 PDFs uploaded thành công (795 qua Python + 3 file lớn retry qua gsutil)
- ✅ Vertex AI Search FULL import triggered (operation `import-documents-11607082215680860780`)
- ✅ Metadata đầy đủ: `user_id`, `scope`, `grade`, `subject`, `doc_type`
- ✅ Breakdown: lop-10/sbt: 326, lop-10/sgk: 48, lop-11/sbt: 165, lop-11/sgk: 73, lop-12/sbt: 124, lop-12/sgk: 62
- ⏳ Cần verify Vertex AI Search indexing hoàn tất

**Lỗi gặp phải trong quá trình triển khai:**

- 403 Forbidden khi truy cập GCS — do `gcloud config project` trỏ nhầm sang `bid-information-484813`. Fix: `gcloud config set project green-mercury-485016-n1` + `gcloud auth application-default set-quota-project`
- 3 file >35MB timeout (120s) khi upload qua Python ThreadPoolExecutor — retry thành công qua `gsutil cp`

**References:**

- [src/services/document_store.py](src/services/document_store.py) — refactor `build_gcs_path()`, `upload_document()`, thêm `doc_type` metadata
- [src/config/constants.py](src/config/constants.py) — thêm `DOC_TYPES` set
- [notebooks/exploration/manage_bucket_data.ipynb](notebooks/exploration/manage_bucket_data.ipynb) — rewrite 8 cells, xóa hardcoded vars
- [notebooks/exploration/download_sbt_pdfs.ipynb](notebooks/exploration/download_sbt_pdfs.ipynb) — notebook tải SBT từ loigiaihay.com
- [notebooks/tests/test_week2_local_session_2026_03_11.ipynb](notebooks/tests/test_week2_local_session_2026_03_11.ipynb) — fix hardcoded bucket name trong mock
- [docs/ai/planning/refactor-bucket-structure-plan.md](docs/ai/planning/refactor-bucket-structure-plan.md) — plan chi tiết 3 decisions + scope of impact

---

### 2026-03-26 — P1: Client-Side Rate Limiting cho LLM Calls

**Vấn đề:** Test `large_30q` chỉ đạt 64.1% pass rate do lỗi 429 (rate limit exceeded). Không có cơ chế kiểm soát tốc độ gọi LLM phía client — batch parsing song song phát ra 4+ lệnh gọi đồng thời vượt quota 60 RPM.

**Nguyên nhân:** Tất cả 8 điểm gọi LLM (`.ainvoke()`) trong pipeline đều gọi trực tiếp Vertex AI API mà không có rate limiting hay concurrency cap.

**Hành động:**

1. Tạo `src/services/rate_limiter.py` — `AsyncTokenBucket` (token bucket async-safe), `CircuitBreaker` (trip sau 5 lỗi 429 liên tiếp, cooldown 60s), `rate_limited_llm_call()` wrapper
2. Thêm config `llm_rate_limit_rpm` (default 60) và `llm_max_concurrent` (default 10) vào `Settings`
3. Wrap `rate_limited_llm_call()` vào 8 điểm gọi LLM: `formatter.py` ×3, `math_agent.py` ×3, `supervisor.py` ×1, `reviewer.py` ×1
4. Lazy initialization singletons — đọc config từ `get_settings()` khi gọi lần đầu

**Kết quả:**

- ✅ Module rate_limiter.py tạo thành công, import OK
- ✅ 8/8 call sites wrapped với rate_limited_llm_call()
- ✅ Config env-configurable qua `LLM_RATE_LIMIT_RPM` và `LLM_MAX_CONCURRENT`
- ⏳ Cần test với `large_30q` để xác nhận lỗi 429 biến mất

**References:**

- [src/services/rate_limiter.py](src/services/rate_limiter.py) — module mới: AsyncTokenBucket, CircuitBreaker, rate_limited_llm_call()
- [src/config/settings.py](src/config/settings.py) — thêm `llm_rate_limit_rpm`, `llm_max_concurrent`
- [src/graph/nodes/formatter.py](src/graph/nodes/formatter.py) — wrap 3 chain.ainvoke() calls
- [src/graph/nodes/math_agent.py](src/graph/nodes/math_agent.py) — wrap 3 ainvoke() calls (code_exec, parse batch, parse single)
- [src/graph/nodes/supervisor.py](src/graph/nodes/supervisor.py) — wrap chain.ainvoke()
- [src/graph/nodes/reviewer.py](src/graph/nodes/reviewer.py) — wrap chain.ainvoke()
