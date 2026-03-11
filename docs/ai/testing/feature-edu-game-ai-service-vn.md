```markdown
---
phase: testing
title: Chiến lược Kiểm thử
description: Định nghĩa phương pháp kiểm thử, test cases, và đảm bảo chất lượng
---

# Chiến lược Kiểm thử

## Kết quả Kiểm thử Notebook (Đã Xác nhận)

> **Cập nhật lần cuối:** 2026-03-11

### test_vertex_search.ipynb — 10/10 code cells PASS ✅

- Vertex AI Search hoạt động với 225 PDFs sách giáo khoa tiếng Việt
- Engine `gp-mathagent_1773042630372` đã nâng cấp lên SEARCH_TIER_ENTERPRISE
- Extractive answers hoạt động, metadata filter đúng
- Cần override `_serving_config` ở engine-level (datastore-level path không hoạt động)

### test_services.ipynb — 11/11 code cells PASS ✅

- Generation LLM (`gemini-2.5-flash`, asia-southeast1) hoạt động ✅
- Review LLM (`gemini-3.1-flash-lite-preview`, global) hoạt động ✅
- Structured output, Vertex AI Search, Firestore CRUD, GCS upload, Cloud Tasks — all PASS ✅
- `usage_metadata` có thể là `dict` — cần dùng `isinstance` check
- `gemini-3.1-flash-lite-preview` chỉ available ở `global` region

### test_graph_pipeline.ipynb — CHƯA CHẠY ⏳

- 14 cells đã tạo, chờ chạy
- Tests: full pipeline E2E, feedback loop, multi-format output

---

## Mục tiêu Coverage

**Chúng ta nhắm đến mức kiểm thử nào?**

- Unit test coverage: **100%** code mới
- Integration: Full LangGraph pipeline E2E, API endpoints, Vertex AI Search, user scoping
- Accuracy: **≥ 98%** đáp án đúng trên golden test set (100 câu)

## Unit Tests

**Những thành phần riêng lẻ nào cần kiểm thử?**

### Pydantic Schemas (api/schemas/)

- [ ] ContentItem: construction hợp lệ, required fields
- [ ] QuizQuestion: cần 4 options, correct_answer_index 0-3
- [ ] Flashcard: front/back hợp lệ, edge cases (empty strings bị reject)
- [ ] FillBlankQuestion: vị trí blank khớp template
- [ ] GenerationRequest: enum validation (game_type), user_id bắt buộc, defaults
- [ ] DocumentRecord: file_format validation (chỉ pdf/docx/pptx)
- [ ] GameContentResponse: nested model serialization/deserialization

### Game Templates (templates/)

- [ ] GAME_TEMPLATES registry: tất cả Phase 1 types được đăng ký
- [ ] Quiz template: content items → QuizQuestion conversion
- [ ] Flashcard template: content items → Flashcard conversion
- [ ] Fill-blank template: content items → FillBlankQuestion conversion
- [ ] Game type không tồn tại → KeyError với message hữu ích

### LLM Service (services/llm.py)

- [ ] Trả về ChatVertexAI Pro khi config=pro
- [ ] Trả về ChatVertexAI Flash khi config=flash
- [ ] Retry logic: 3x với exponential backoff (mock API errors)
- [ ] Token usage tracking chính xác

### Vertex AI Search Service (services/vertex_search.py)

- [ ] Trả về VertexAISearchRetriever đã cấu hình với user_id filter (doc_scope="user")
- [ ] Trả về VertexAISearchRetriever đã cấu hình với `__system__` filter (doc_scope="system")
- [ ] Trả về combined filter `ANY(user_id, __system__)` (doc_scope="all")
- [ ] User-first re-ranking: doc_scope="all" → user docs xếp trước system docs
- [ ] Xử lý kết quả rỗng gracefully
- [ ] Tuân theo max_documents config
- [ ] Default doc_scope là "all"

### Document Store Service (services/document_store.py)

- [ ] Upload PDF (user) → GCS correct path: `user/{user_id}/{date}/{session}/`
- [ ] Upload PDF (admin/system) → GCS correct path: `system/{date}/{session}/`
- [ ] Upload DOCX → GCS correct path
- [ ] Upload PPTX → GCS correct path
- [ ] Reject files không phải PDF/DOCX/PPTX → 400
- [ ] Reject files > 50MB → 413
- [ ] Trigger Data Store import với metadata (bao gồm scope: "user" hoặc "system")
- [ ] GCS metadata bao gồm user_id (hoặc `__system__`), upload_date, session_id, scope

### Supervisor Node (graph/nodes/supervisor.py)

- [ ] Nhận request và extract routing info
- [ ] Xác định doc_scope từ request (default: "all")
- [ ] Route tới math_agent (Phase 1: Toán/Lý/Hóa)
- [ ] Truyền user_id, topic, game_types, doc_scope vào state

### Math Agent Node (graph/nodes/math_agent.py)

- [ ] Query VertexAISearchRetriever với doc_scope filter
- [ ] doc_scope="user" → chỉ query user docs
- [ ] doc_scope="system" → chỉ query system docs
- [ ] doc_scope="all" → query cả user + system docs, user docs xuất hiện trước
- [ ] Generate content items (generic Q&A format)
- [ ] Dùng Code Execution cho math/physics/chemistry computation
- [ ] Xử lý difficulty levels
- [ ] Tuân theo num_questions từ request

### Reviewer Node (graph/nodes/reviewer.py)

- [ ] Approve content items đúng (pass)
- [ ] Reject đáp án sai (fail + reason)
- [ ] Reject content không grounded trong user's docs
- [ ] Trả về structured feedback per item

### Formatter Node (graph/nodes/formatter.py)

- [ ] Load đúng template per game_type từ registry
- [ ] Transform content items → QuizQuestion (structured output)
- [ ] Transform content items → Flashcard (structured output)
- [ ] Transform content items → FillBlankQuestion (structured output)
- [ ] Xử lý nhiều game_types trong một request
- [ ] Deduplication hoạt động
- [ ] Empty input → empty output (không crash)

## Integration Tests

**Làm sao kiểm thử tương tác giữa các thành phần?**

- [ ] **Full LangGraph pipeline:** Supervisor → Math Agent → Reviewer → Formatter (với real Vertex AI)
- [ ] **Feedback loop:** Reviewer reject → Supervisor → Math Agent retry → Reviewer pass
- [ ] **Max retry:** Sau 3 iterations, trả về partial results gracefully
- [ ] **Multi game type:** Request Quiz + Flashcard → cả hai types trong response
- [ ] **User scoping:** User A documents → query chỉ trả về User A content (không User B)
- [ ] **System docs access:** Bất kỳ user với doc_scope="system" hoặc "all" → có thể query system docs
- [ ] **Admin upload E2E:** POST /api/v1/admin/documents/upload → GCS `system/` + Firestore + AI Search
- [ ] **Admin list:** GET /api/v1/admin/documents → trả về system docs list
- [ ] **Admin delete:** DELETE /api/v1/admin/documents/{document_id} → xóa system doc
- [ ] **Service auth:** Cloud Run IAM — chỉ upstream service gọi được AI Service, unauthorized caller → 403
- [ ] **API E2E:** POST /api/v1/generate → valid GameContentResponse
- [ ] **Generate with doc_scope:** doc_scope="user" / "system" / "all" → scoping đúng
- [ ] **User-first verification:** doc_scope="all" → response content ưu tiên user docs hơn system docs
- [ ] **Document upload E2E:** POST /api/v1/documents/upload → GCS (đúng folder) + Firestore record + AI Search import
- [ ] **Multi-format upload:** PDF, DOCX, PPTX tất cả index thành công
- [ ] **Firestore persistence:** Generated content được lưu và retrievable qua GET
- [ ] **User doc listing:** GET /api/v1/users/{user_id}/documents chỉ trả về docs của user đó

## End-to-End Tests

**Những user flows nào cần validation?**

- [ ] Happy path: Upload giáo án PDF → Generate 10 Quiz → All pass review → Valid JSON
- [ ] **No-upload path:** User chưa upload gì + doc_scope="system" → Generate Quiz từ system docs → Valid JSON
- [ ] **No-upload default:** User chưa upload + doc_scope="all" → fallback sang system docs → thành công
- [ ] **Admin upload:** Admin upload SGK → system doc được indexed → tất cả users có thể generate từ đó
- [ ] DOCX flow: Upload giáo trình DOCX → Generate Flashcards → Valid
- [ ] PPTX flow: Upload slide PPTX → Generate Fill-blank → Valid
- [ ] Mixed types: Request Quiz + Flashcard + Fill-blank → Cả 3 types có mặt
- [ ] Difficulty: Request easy/medium/hard → Content phản ánh difficulty
- [ ] Large document: 200-page PDF → Success (không timeout)
- [ ] Multi-user isolation: User A upload → User B doc_scope="user" không query được → empty
- [ ] System docs shared: User A + User B đều query được doc_scope="system" hoặc "all"
- [ ] **User-first E2E:** Upload cả user doc + system doc → doc_scope="all" → user doc content xuất hiện trước trong kết quả
- [ ] Error: Upload file .txt → 400 với "Định dạng hỗ trợ: PDF, DOCX, PPTX"
- [ ] Error: Upload > 50MB → 413
- [ ] Error: Generate từ indexing chưa xong → 409 "Document đang được index"
- [ ] Error: doc_scope="user" nhưng user không có docs → 400 "Không tìm thấy user documents. Sử dụng doc_scope=system hoặc all."
- [ ] Error: Unauthorized caller (không có Cloud Run IAM) → 403
- [ ] Game types endpoint: GET /api/v1/game-types → list với schemas

## Dữ liệu Test

**Chúng ta dùng dữ liệu gì để test?**

### Fixtures

- SGK Toán 11 PDF: chương "Đạo hàm" (system doc)
- SGK Vật lý 12 PDF: chương "Động lực học" (system doc)
- Giáo án Toán 11 PDF: chương "Đạo hàm" (user doc)
- Giáo trình Vật lý DOCX: chương "Động lực học" (user doc)
- Slide bài giảng Hóa PPTX: chương "Cân bằng phương trình" (user doc)

### Mocks (cho unit tests nhanh)

- Mock `ChatVertexAI` responses
- Mock `VertexAISearchRetriever` results (với xác minh doc_scope filter)
- Mock Firestore client
- Mock GCS client
- Mock game templates (xác minh đúng template được chọn theo game type)

### Golden Test Set

- 100 câu hỏi từ giáo án/giáo trình với đáp án đã verified
- Covers: Toán (đạo hàm, tích phân), Lý (động lực học), Hóa (cân bằng)
- Dùng cho đo lường accuracy: target ≥ 98%

## Báo cáo Test & Coverage

**Làm sao xác minh và truyền đạt kết quả test?**

- Tool: `pytest` + `pytest-cov` + `pytest-asyncio`
- Chạy: `pytest --cov=src --cov-report=html --cov-fail-under=90`
- Báo cáo accuracy: custom script so sánh generated vs golden answers
- CI: fail nếu coverage < 90% hoặc accuracy < 98%

## Kiểm thử Thủ công

**Những gì cần validation từ con người?**

- [ ] Chất lượng ngôn ngữ tiếng Việt (tự nhiên, đúng ngữ pháp)
- [ ] Distractors hợp lý (đáp án sai không quá hiển nhiên)
- [ ] Flashcard front đủ ngắn, back đủ chi tiết
- [ ] Fill-blank chỗ trống ở vị trí hợp lý
- [ ] Content grounding: output bám sát tài liệu (system docs hoặc user upload), không hallucinate
- [ ] DOCX/PPTX extraction quality: text trích xuất đúng, không bị lỗi format
- [ ] Multi-user: verify User A không thấy documents User B (nhưng cả hai thấy system docs)
- [ ] Admin upload: system docs xuất hiện cho tất cả users
- [ ] Game template output phù hợp dạng game
- [ ] Game Client team verify JSON consume được

## Kiểm thử Hiệu suất

**Làm sao validate performance?**

- [ ] Latency: 10 câu < 60s (10 runs, p95)
- [ ] Latency: 50 câu batch < 5 phút
- [ ] Concurrent: 10 requests đồng thời → tất cả thành công
- [ ] Cloud Run cold start < 15s
- [ ] Vertex AI Search query < 2s (p95)
- [ ] Document indexing: PDF 50MB < 15 phút
- [ ] Document indexing: DOCX/PPTX 50MB < 15 phút

## Theo dõi Bug

**Làm sao quản lý issues?**

- GitHub Issues: `bug`, `accuracy`, `performance`, `api`, `user-scoping`, `game-template`, `admin`, `system-docs`
- Severity:
  - **Critical:** Đáp án sai, rò rỉ dữ liệu user (cross-user), JSON schema mismatch, Cloud Run IAM bypass
  - **Major:** Timeout, chất lượng kém, AI Search miss, format extraction fail, system docs không truy cập được
  - **Minor:** Formatting, chậm nhưng hoạt động, cosmetic
- Regression: Chạy lại golden test set trước mỗi release
```
