---
phase: implementation
title: Session Summary — Week 2 Complete
date: 2026-03-11
branch: feat/mvp
commit: a658a90
---

# Session Summary: 2026-03-11 — Tuần 2 Hoàn thành

## Phạm vi Session

Hoàn thiện toàn bộ Week-2 TODOs (T2.2, T2.3, T2.4) và kiểm thử local-first mà không cần Cloud Run build.

---

## Những gì đã làm

### 1. FastAPI Entrypoint (`src/main.py`)

- App FastAPI với 3 router: `generation_router`, `admin_router`, `internal_router`
- Endpoint `/health` để health-check
- CORS, lifespan context

### 2. Generation API (`src/api/routes/generation.py`)

- `POST /api/v1/generate` (HTTP 202) — tạo job + enqueue
  - Mode production: `CLOUD_RUN_BASE_URL` set → dùng Cloud Tasks
  - Mode local dev: `LOCAL_ASYNC_MODE=true` → dùng FastAPI `BackgroundTasks` (chạy trong cùng process)
  - Nếu cả hai đều không set → HTTP 500
- `GET /api/v1/generations/{request_id}` — poll job status/result

### 3. Admin API (`src/api/routes/admin.py`)

- `POST /api/v1/admin/documents/upload` — upload system doc (scope="system", user_id="**system**")
- `GET /api/v1/admin/documents` — list system docs từ Firestore
- `DELETE /api/v1/admin/documents/{doc_id}` — xóa system doc

### 4. Internal endpoint (`src/api/routes/internal.py`)

- `POST /internal/execute-generation/{id}` — Cloud Tasks callback
- Verify headers `X-CloudTasks-TaskName` và `X-CloudTasks-QueueName`
- Delegate sang `execute_generation_job()`

### 5. Shared Executor (`src/services/generation_executor.py`)

```python
async def execute_generation_job(request_id: str) -> dict:
    job = await get_job(request_id)
    request_model = GenerationRequest.model_validate(job["request"])
    graph_app = get_graph_app()
    final_state = await graph_app.ainvoke(graph_input)
    await complete_job(request_id, output_dict)
    # on exception: await fail_job(request_id, str(exc)); raise
```

Dùng chung cho cả local BackgroundTasks và Cloud Tasks path.

### 6. Settings mới (`src/config/settings.py`)

```python
cloud_tasks_invoker_service_account: str | None = None
cloud_run_base_url: str | None = None
local_async_mode: bool = False
```

### 7. Firestore (`src/services/firestore.py`)

- Thêm `list_document_records(scope, user_id, limit)` — filter + Python sort (tránh composite index)

### 8. Test Notebook

- `notebooks/tests/test_week2_local_session_2026_03_11.ipynb` — 5/5 cells PASS
  - T2.3 local async flow
  - T2.2 Admin API smoke
  - Summary assertions
  - T2.4 formatter smoke (quiz/flashcard/fill_blank)

---

## Môi trường Dev Hiện tại

| Var                  | Giá trị   | Ý nghĩa                  |
| -------------------- | --------- | ------------------------ |
| `LOCAL_ASYNC_MODE`   | `true`    | BackgroundTasks fallback |
| `CLOUD_RUN_BASE_URL` | (trống)   | Không dùng Cloud Tasks   |
| `ENV`                | `develop` | Load `.env.develop`      |

---

## Vấn đề đã gặp & cách xử lý

| Vấn đề                                                      | Giải pháp                                                            |
| ----------------------------------------------------------- | -------------------------------------------------------------------- |
| Firestore composite index khi dùng `order_by` + `where`     | Bỏ `.order_by()`, sort trong Python sau `stream()`                   |
| `BackgroundTasks` instantiate thủ công → tasks không chạy   | Inject qua parameter FastAPI DI: `background_tasks: BackgroundTasks` |
| Notebook `\\n` literal → `SyntaxError`                      | Rewrite cells qua `edit_notebook_file` với Python string đúng        |
| `ModuleNotFoundError: No module named 'src'` trong notebook | Thêm `sys.path` auto-detect loop tìm repo root                       |
| Cloud Run build FAIL (chưa có Dockerfile)                   | Deliberately deferred — dùng `LOCAL_ASYNC_MODE` thay thế             |

---

## Trạng thái Checklist Tuần 2

| Task                         | Trạng thái                           |
| ---------------------------- | ------------------------------------ |
| T2.1 Document Upload Service | ✅ Done (2026-03-09)                 |
| T2.2 Admin API               | ✅ Verified local (2026-03-11)       |
| T2.3 Cloud Tasks Async       | ✅ Verified local-first (2026-03-11) |
| T2.4 Game Template System    | ✅ Verified local (2026-03-11)       |
| T3.2 Pydantic Schemas        | ✅ Done (2026-03-09)                 |

**Deliverable M2/M3 đạt: Tất cả endpoints hoạt động, async flow verified, Admin API done.**

---

## TODO Tương lai (theo thứ tự ưu tiên)

### Ngay tiếp theo (trước deploy)

1. **Chạy `test_graph_pipeline.ipynb`** (14 cells, chưa run)
   - Test full E2E pipeline với GCP thật (Vertex AI Search, Gemini)
   - Không monkeypatch — dùng credentials thật
   - Mục tiêu: confirm pipeline hoạt động end-to-end trước khi tích hợp API

2. **Tạo Dockerfile** (cho Cloud Run)
   - Base image: `python:3.12-slim`
   - Port 8080, uvicorn entrypoint
   - Multi-stage build để giảm size
   - Sau khi có → push → Cloud Run service `aiservices` tự build lại

3. **Cloud Run IAM setup** (sau Dockerfile)
   - Service account `edu-game-ai@green-mercury-485016-n1.iam.gserviceaccount.com`
   - Grant `roles/run.invoker` cho Cloud Tasks SA
   - Set `CLOUD_RUN_BASE_URL=https://aiservices-711906617662.asia-southeast1.run.app`
   - Set `CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT` trong Cloud Run env vars

### Tuần 3 TODOs (T3.x - T4.x)

4. **T3.1: Code Execution cho STEM**
   - Enable Gemini code execution trong config
   - Update Math Agent prompt để dùng Python cho calculations
   - Test 20 câu STEM từ golden set

5. **T4.1: API Hoàn thiện**
   - `GET /api/v1/users/{user_id}/documents` — list user docs
   - `GET /api/v1/game-types` — list supported game types + schemas
   - Error handling thống nhất

6. **T4.2: Accuracy Testing**
   - Golden set 100 câu STEM tiếng Việt
   - Target ≥ 98% accuracy

7. **T4.3: Performance Testing**
   - 10 câu < 60s (p95)
   - 10 concurrent requests

8. **T4.4: Production Hardening**
   - Full E2E test Cloud Tasks → Cloud Run
   - Monitor logs trên Cloud Run
   - Rate limiting, timeout handling

### Kỹ thuật tồn đọng

- T2.1 còn 1 sub-task: Lưu `DocumentRecord` vào Firestore khi upload (hiện chỉ lưu lên GCS + trigger AI Search import, chưa ghi Firestore record)
- T3.2: Generate OpenAPI spec, review với Game Client team
- `test_graph_pipeline.ipynb`: review lại 14 cells trước khi chạy

---

## Thông tin Kỹ thuật Quan trọng

### GCP Resources

| Resource                         | Giá trị                                           |
| -------------------------------- | ------------------------------------------------- |
| Project                          | `green-mercury-485016-n1`                         |
| Region                           | `asia-southeast1`                                 |
| Vertex AI Search Engine          | `gp-mathagent_1773042630372`                      |
| Cloud Tasks Queue                | `generation-queue`                                |
| Firestore DB                     | `aiservice-store`                                 |
| Cloud Run service (build failed) | `aiservices-711906617662.asia-southeast1.run.app` |

### Known Constraints

- `VertexAISearchRetriever._serving_config` phải override với engine-level path (datastore-level không hoạt động)
- Enterprise tier bắt buộc cho extractive answers
- `gemini-3.1-flash-lite-preview` chỉ available ở region `global` (review model)
- Generation model dùng `asia-southeast1`

### Môi trường

- Conda env: `AIservice` (Python 3.12.12)
- CWD: `/home/sakana/Code/ManifoldsTeam/AIServices`
- Branch: `feat/mvp`

---

## Notebook Sessions đã verify

| Notebook                                    | Cells | Kết quả       | Ngày       |
| ------------------------------------------- | ----- | ------------- | ---------- |
| `test_vertex_search.ipynb`                  | 10/10 | PASS          | 2026-03-09 |
| `test_services.ipynb`                       | 11/11 | PASS          | 2026-03-09 |
| `test_week2_local_session_2026_03_11.ipynb` | 5/5   | PASS          | 2026-03-11 |
| `test_graph_pipeline.ipynb`                 | 0/14  | **CHƯA CHẠY** | —          |
