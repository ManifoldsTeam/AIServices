---
phase: testing
title: Testing Strategy
description: Define testing approach, test cases, and quality assurance
---

# Testing Strategy

## Test Coverage Goals

**What level of testing do we aim for?**

- Unit test coverage: **100%** of new code
- Integration: Full LangGraph pipeline E2E, API endpoints, Vertex AI Search, user scoping
- Accuracy: **≥ 98%** correct answers on golden test set (100 questions)

## Unit Tests

**What individual components need testing?**

### Pydantic Schemas (api/schemas/)

- [ ] ContentItem: valid construction, required fields
- [ ] QuizQuestion: 4 options required, correct_answer_index 0-3
- [ ] Flashcard: valid front/back, edge cases (empty strings rejected)
- [ ] FillBlankQuestion: blank positions match template
- [ ] GenerationRequest: enum validation (game_type), user_id required, defaults
- [ ] DocumentRecord: file_format validation (pdf/docx/pptx only)
- [ ] GameContentResponse: nested model serialization/deserialization

### Game Templates (templates/)

- [ ] GAME_TEMPLATES registry: all MVP types registered
- [ ] Quiz template: content items → QuizQuestion conversion
- [ ] Flashcard template: content items → Flashcard conversion
- [ ] Fill-blank template: content items → FillBlankQuestion conversion
- [ ] Unknown game type → KeyError with helpful message

### LLM Service (services/llm.py)

- [ ] Returns ChatVertexAI Pro when config=pro
- [ ] Returns ChatVertexAI Flash when config=flash
- [ ] Retry logic: 3x with exponential backoff (mock API errors)
- [ ] Token usage tracking accuracy

### Vertex AI Search Service (services/vertex_search.py)

- [ ] Returns configured VertexAISearchRetriever with user_id filter (doc_scope="user")
- [ ] Returns configured VertexAISearchRetriever with `__system__` filter (doc_scope="system")
- [ ] Returns combined filter `ANY(user_id, __system__)` (doc_scope="all")
- [ ] User-first re-ranking: doc_scope="all" → user docs xếp trước system docs
- [ ] Handles empty results gracefully
- [ ] Respects max_documents config
- [ ] Default doc_scope is "all"

### Document Store Service (services/document_store.py)

- [ ] Upload PDF (user) → GCS correct path: `user/{user_id}/{date}/{session}/`
- [ ] Upload PDF (admin/system) → GCS correct path: `system/{date}/{session}/`
- [ ] Upload DOCX → GCS correct path
- [ ] Upload PPTX → GCS correct path
- [ ] Rejects non-PDF/DOCX/PPTX files → 400
- [ ] Rejects > 50MB files → 413
- [ ] Triggers Data Store import with metadata (includes scope: "user" or "system")
- [ ] GCS metadata includes user_id (or `__system__`), upload_date, session_id, scope

### Supervisor Node (graph/nodes/supervisor.py)

- [ ] Receives request and extracts routing info
- [ ] Determines doc_scope from request (default: "all")
- [ ] Routes to content_agent (MVP: single path)
- [ ] Passes user_id, topic, game_types, doc_scope to state

### Content Agent Node (graph/nodes/content_agent.py)

- [ ] Queries VertexAISearchRetriever with doc_scope filter
- [ ] doc_scope="user" → only user docs queried
- [ ] doc_scope="system" → only system docs queried
- [ ] doc_scope="all" → both user + system docs queried, user docs xuất hiện trước
- [ ] Generates content items (generic Q&A format)
- [ ] Uses Code Execution for math/physics/chemistry computation
- [ ] Handles difficulty levels
- [ ] Respects num_questions from request

### Reviewer Node (graph/nodes/reviewer.py)

- [ ] Approves correct content items (pass)
- [ ] Rejects wrong answers (fail + reason)
- [ ] Rejects content not grounded in user's docs
- [ ] Returns structured feedback per item

### Formatter Node (graph/nodes/formatter.py)

- [ ] Loads correct template per game_type from registry
- [ ] Transforms content items → QuizQuestion (structured output)
- [ ] Transforms content items → Flashcard (structured output)
- [ ] Transforms content items → FillBlankQuestion (structured output)
- [ ] Handles multiple game_types in single request
- [ ] Deduplication works
- [ ] Empty input → empty output (no crash)

## Integration Tests

**How do we test component interactions?**

- [ ] **Full LangGraph pipeline:** Supervisor → Content Agent → Reviewer → Formatter (with real Vertex AI)
- [ ] **Feedback loop:** Reviewer rejects → Supervisor → Content Agent retries → Reviewer passes
- [ ] **Max retry:** After 3 iterations, returns partial results gracefully
- [ ] **Multi game type:** Request Quiz + Flashcard → both types in response
- [ ] **User scoping:** User A documents → query returns only User A content (not User B)
- [ ] **System docs access:** Any user with doc_scope="system" or "all" → can query system docs
- [ ] **Admin upload E2E:** POST /api/v1/admin/documents/upload → GCS `system/` + Firestore + AI Search
- [ ] **Admin list:** GET /api/v1/admin/documents → returns system docs list
- [ ] **Admin delete:** DELETE /api/v1/admin/documents/{document_id} → removes system doc
- [ ] **Admin auth:** Admin endpoints require X-Admin-Key, reject with 403 otherwise
- [ ] **API E2E:** POST /api/v1/generate → valid GameContentResponse
- [ ] **Generate with doc_scope:** doc_scope="user" / "system" / "all" → correct scoping
- [ ] **User-first verification:** doc_scope="all" → response content prioritizes user docs over system docs
- [ ] **Document upload E2E:** POST /api/v1/documents/upload → GCS (correct folder) + Firestore record + AI Search import
- [ ] **Multi-format upload:** PDF, DOCX, PPTX all index successfully
- [ ] **Firestore persistence:** Generated content saved and retrievable via GET
- [ ] **User doc listing:** GET /api/v1/users/{user_id}/documents returns only that user's docs

## End-to-End Tests

**What user flows need validation?**

- [ ] Happy path: Upload giáo án PDF → Generate 10 Quiz → All pass review → Valid JSON
- [ ] **No-upload path:** User chưa upload gì + doc_scope="system" → Generate Quiz từ system docs → Valid JSON
- [ ] **No-upload default:** User chưa upload + doc_scope="all" → fallback to system docs → success
- [ ] **Admin upload:** Admin upload SGK → system doc indexed → all users can generate from it
- [ ] DOCX flow: Upload giáo trình DOCX → Generate Flashcards → Valid
- [ ] PPTX flow: Upload slide PPTX → Generate Fill-blank → Valid
- [ ] Mixed types: Request Quiz + Flashcard + Fill-blank → All 3 types present
- [ ] Difficulty: Request easy/medium/hard → Content reflects difficulty
- [ ] Large document: 200-page PDF → Success (no timeout)
- [ ] Multi-user isolation: User A upload → User B doc_scope="user" cannot query → empty
- [ ] System docs shared: User A + User B both can query doc_scope="system" or "all"
- [ ] **User-first E2E:** Upload cả user doc + system doc → doc_scope="all" → user doc content xuất hiện trước trong kết quả
- [ ] Error: Upload .txt file → 400 with "Supported formats: PDF, DOCX, PPTX"
- [ ] Error: Upload > 50MB → 413
- [ ] Error: Generate from unfinished indexing → 409 "Document still indexing"
- [ ] Error: doc_scope="user" but user has no docs → 400 "No user documents found. Use doc_scope=system or all."
- [ ] Error: Admin endpoint without X-Admin-Key → 403
- [ ] Game types endpoint: GET /api/v1/game-types → list with schemas

## Test Data

**What data do we use for testing?**

### Fixtures

- SGK Toán 11 PDF: chương "Đạo hàm" (system doc)
- SGK Vật lý 12 PDF: chương "Động lực học" (system doc)
- Giáo án Toán 11 PDF: chương "Đạo hàm" (user doc)
- Giáo trình Vật lý DOCX: chương "Động lực học" (user doc)
- Slide bài giảng Hóa PPTX: chương "Cân bằng phương trình" (user doc)

### Mocks (for fast unit tests)

- Mock `ChatVertexAI` responses
- Mock `VertexAISearchRetriever` results (with doc_scope filter verification)
- Mock Firestore client
- Mock GCS client
- Mock game templates (verify correct template selected per game type)

### Golden Test Set

- 100 câu hỏi từ giáo án/giáo trình với đáp án verified
- Covers: Toán (đạo hàm, tích phân), Lý (động lực học), Hóa (cân bằng)
- Used for accuracy measurement: target ≥ 98%

## Test Reporting & Coverage

**How do we verify and communicate test results?**

- Tool: `pytest` + `pytest-cov` + `pytest-asyncio`
- Run: `pytest --cov=src --cov-report=html --cov-fail-under=90`
- Accuracy report: custom script comparing generated vs golden answers
- CI: fail if coverage < 90% or accuracy < 98%

## Manual Testing

**What requires human validation?**

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

## Performance Testing

**How do we validate performance?**

- [ ] Latency: 10 câu < 60s (10 runs, p95)
- [ ] Latency: 50 câu batch < 5 phút
- [ ] Concurrent: 10 simultaneous requests → all succeed
- [ ] Cloud Run cold start < 15s
- [ ] Vertex AI Search query < 2s (p95)
- [ ] Document indexing: PDF 50MB < 15 phút
- [ ] Document indexing: DOCX/PPTX 50MB < 15 phút

## Bug Tracking

**How do we manage issues?**

- GitHub Issues: `bug`, `accuracy`, `performance`, `api`, `user-scoping`, `game-template`, `admin`, `system-docs`
- Severity:
  - **Critical:** Wrong answer, user data leak (cross-user), JSON schema mismatch, admin key leak
  - **Major:** Timeout, poor quality, AI Search miss, format extraction fail, system docs not accessible
  - **Minor:** Formatting, slow but functional, cosmetic
- Regression: Re-run golden test set before each release
