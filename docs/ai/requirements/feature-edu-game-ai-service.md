---
phase: requirements
title: Requirements & Problem Understanding
description: Clarify the problem space, gather requirements, and define success criteria
---

# Requirements & Problem Understanding

## Problem Statement

**What problem are we solving?**

### Bối cảnh

Việc tạo nội dung cho game giáo dục vẫn phụ thuộc hoàn toàn vào con người — giáo viên hoặc content creator phải viết tay từng câu hỏi, đáp án, giải thích. Quy trình này:

- **Tốn thời gian:** Tạo 100 câu Quiz chất lượng cho 1 chương mất hàng ngày công.
- **Khó scale:** Mỗi môn, mỗi chương, mỗi giáo viên đều có tài liệu riêng.
- **Chất lượng không đồng đều:** Đặc biệt với các bài tính toán khi đáp án có thể sai.
- **Thiếu đa dạng:** Khó tạo nhiều dạng game (Quiz, Flashcard, Adventure, Matching...) từ cùng một nguồn tài liệu.

### Vấn đề cốt lõi

Cần một **AI Service** tự động có khả năng:

1. **Có sẵn kho tài liệu nền tảng** (system/shared) do Admin quản lý — SGK, giáo trình chuẩn, tài liệu tham khảo — để hệ thống hoạt động được ngay cả khi user chưa upload gì.
2. **Nhận tài liệu của người dùng** (giáo án, giáo trình, slide bài giảng, đề cương — PDF/DOCX/PPTX) — bổ sung vào nguồn kiến thức cá nhân.
3. **Đọc hiểu và index** tài liệu qua Vertex AI Search (cả system docs lẫn user docs).
4. **Sinh nội dung game giáo dục** (JSON) dựa trên tài liệu — ưu tiên user docs nếu có, fallback sang system docs nếu không.

Tất cả các dạng game đều là **Q&A-based** ở lớp nền tảng (hỏi-đáp, khái niệm, matching...). Hệ thống sinh **educational content items** → format theo **game template** tương ứng.

### Hai nguồn tài liệu

| Nguồn           | Ai quản lý | Mục đích                                                    | GCS prefix        |
| --------------- | ---------- | ----------------------------------------------------------- | ----------------- |
| **System docs** | Admin      | Kho tài liệu nền tảng (SGK, giáo trình chuẩn) — luôn có sẵn | `system/`         |
| **User docs**   | User       | Tài liệu cá nhân (giáo án, slide, đề cương riêng)           | `user/{user_id}/` |

### Ai bị ảnh hưởng?

- **Admin:** Quản lý kho tài liệu nền tảng (system docs) — SGK, giáo trình chuẩn, tài liệu tham khảo.
- **Giáo viên:** Upload giáo án/giáo trình của mình → nhận game content tự động. Hoặc dùng luôn system docs nếu chưa có tài liệu riêng.
- **Content creators:** Tạo game giáo dục nhanh từ tài liệu có sẵn (system hoặc cá nhân).
- **Học sinh/Sinh viên:** Có game học tập đa dạng, bám sát bài giảng.
- **Đội ngũ phát triển game:** Có nguồn nội dung phong phú, chuẩn hóa JSON.

### Tại sao GCP + Vertex AI Search?

Team **không có sẵn hạ tầng** → cần 100% Managed Services:

- **Vertex AI Search** (Discovery Engine) — thay thế hoàn toàn RAG pipeline tự build (không cần pgvector, chunking, embedding).
- **Gemini** Native Agentic + Code Execution → giảm đáng kể code cần viết.
- GCP project `green-mercury-485016-n1` — APIs đã được enable, cần setup resources (Data Store, bucket, Firestore, Service Account).

## Goals & Objectives

**What do we want to achieve?**

### Primary Goals

1. **Dual document sources:** System docs (Admin quản lý, luôn có sẵn) + User docs (cá nhân, optional). User có thể sinh game ngay mà không cần upload — dùng system docs.
2. **User-centric document management:** Mỗi user upload tài liệu của mình → hệ thống index và scope query theo user. GCS bucket structure: `user/{user_id}/{YYYY-MM-DD}/{session_id}/`.
3. **Flexible game type system:** Tất cả game types đều Q&A-based → hệ thống sinh **content items** (câu hỏi, khái niệm, fact) → **game template** transform thành format cụ thể. Thêm game type mới = thêm template schema + prompt.
4. **LangGraph là core orchestration duy nhất** cho toàn bộ business logic. Mở rộng nghiệp vụ = thêm node/edge vào graph.
5. **Vertex AI Search thay thế RAG pipeline** — upload docs → Data Store auto-index → query qua `VertexAISearchRetriever`. Zero custom indexing code.
6. **Hỗ trợ 3 format input:** PDF, DOCX, PPTX.
7. **Feedback loop trong LangGraph:** Supervisor → Agent → Reviewer → reject → retry (max 3 lần).

### Secondary Goals

- LangGraph graph extensible: thêm agent mới (Story, Visual) chỉ cần thêm node + conditional edge.
- REST API cho Game Client.
- Structured logging qua GCP Cloud Logging.

### Non-Goals (Out of Scope cho MVP)

- ❌ Build RAG pipeline riêng (dùng Vertex AI Search).
- ❌ Setup Vector DB (pgvector, Chroma, etc).
- ❌ Xử lý hình ảnh/bản đồ trong tài liệu (Phase 3 — Visual Agent).
- ❌ Game Client/Frontend.
- ❌ User auth phức tạp (OAuth2, JWT) — MVP dùng API Key + user_id header. Admin dùng `X-Admin-Key`.
- ❌ Real-time streaming.
- ❌ User tiers / pricing tiers (free vs premium) — MVP không phân biệt tier. Monitor usage trước, xem xét tier sau.

## User Stories & Use Cases

**How will users interact with the solution?**

### User Stories

**US-1: Admin upload tài liệu nền tảng (System docs)**

> Là một **Admin**, tôi muốn upload SGK Toán 11, Lý 12, Hóa 10 (PDF/DOCX/PPTX) vào kho tài liệu chung (system docs) → để tất cả user có thể sinh game từ đó ngay mà không cần upload gì.

**US-2: Admin quản lý system docs**

> Là một **Admin**, tôi muốn xem danh sách, xóa, thêm tài liệu trong kho system docs → quản lý chất lượng nguồn tài liệu nền tảng.

**US-3: User sinh game không cần upload (dùng system docs)**

> Là một **Giáo viên**, tôi chưa có giáo án riêng nhưng muốn sinh 10 câu Quiz chương "Đạo hàm" Toán 11 → hệ thống dùng SGK có sẵn (system docs) → trả JSON game content.

**US-4: Upload tài liệu cá nhân**

> Là một **Giáo viên**, tôi muốn upload giáo án Toán 11 (PDF/DOCX/PPTX) → hệ thống index tài liệu vào workspace của tôi → tôi có thể sinh game content từ đó.

**US-5: Sinh Quiz từ giáo trình cá nhân**

> Là một **Giáo viên**, tôi muốn chọn chương "Đạo hàm" từ tài liệu đã upload → sinh 20 câu trắc nghiệm (đáp án tính bằng Code Execution) → trả JSON cho game engine.

**US-6: Sinh Flashcard từ slide bài giảng**

> Là một **Content Creator**, tôi muốn upload slide Vật lý "Động lực học" → sinh Flashcard (mặt trước: công thức, mặt sau: giải thích + ví dụ) từ nội dung slide.

**US-7: Sinh game Adventure Q&A** _(Phase 2)_

> Là một **Game Developer**, tôi muốn sinh nội dung cho game phiêu lưu: narrative intro → branching Q&A → player chọn đáp án đúng để tiến tiếp → tất cả dựa trên tài liệu Hóa học (system hoặc user docs).

**US-8: Sinh nhiều dạng game cùng lúc**

> Là một **Giáo viên**, tôi muốn chọn 1 chương → sinh đồng thời Quiz + Flashcard + Fill-in-blank + Matching → nhận tất cả trong 1 response JSON.

**US-9: Quality control**

> Là một **QA Engineer**, tôi muốn mỗi câu hỏi đều qua Reviewer node trong LangGraph, đảm bảo tỷ lệ sai < 2%.

**US-10: Tùy chỉnh parameters**

> Là một **User**, tôi muốn chỉ định: số lượng, mức độ khó, dạng game, chương/chủ đề, để nhận output phù hợp nhu cầu.

### Key Workflow

```
Flow A — Admin thêm system docs:
   1. Admin: POST /api/v1/admin/documents/upload { file, subject, grade }
      → Upload GCS: gs://bucket/system/{YYYY-MM-DD}/{session_id}/{filename}
      → Import Vertex AI Search Data Store (metadata: user_id="__system__", subject, grade)
      → Auto-index (~10-15 phút)

Flow B — User upload tài liệu cá nhân:
   1. User upload tài liệu (PDF/DOCX/PPTX):
      → API nhận file → validate format
      → Upload GCS: gs://bucket/user/{user_id}/{YYYY-MM-DD}/{session_id}/{filename}
      → Import vào Vertex AI Search Data Store (metadata: user_id, upload_date, subject)
      → Auto-index (~10-15 phút)

Flow C — Generate game content:
   1. User: POST /api/v1/generate {
        user_id, topic/chapter, game_types[], difficulty, num_questions,
        doc_scope: "user" | "system" | "all" (default: "all")
      }

   2. LangGraph graph chạy:
      a. Supervisor: nhận request → xác định doc_scope → routing
      b. Content Agent: query VertexAISearchRetriever
         - doc_scope="user": filter user_id only
         - doc_scope="system": filter user_id="__system__" only
         - doc_scope="all": query cả hai → post-retrieval re-ranking
           (user docs xếp trước, system docs bổ sung)
         → lấy context → sinh content items
         → Code Execution cho tính toán nếu cần
      c. Reviewer (Gemini Flash): kiểm tra chất lượng, grounding
      d. Fail → feedback loop về Supervisor (max 3 lần)
      e. Formatter: nhận content items + game_types[]
         → transform theo game template tương ứng
         → output JSON chuẩn Pydantic

   3. Lưu Firestore → trả API response
```

### Game Types — Q&A Foundation

Tất cả game types đều dựa trên **educational content items** ở lớp cơ sở:

| Game Type         | Bản chất Q&A                    | Output Structure                                                |
| ----------------- | ------------------------------- | --------------------------------------------------------------- |
| **Quiz**          | Câu hỏi + 4 options + 1 correct | `{ question, options[], correct_index, explanation }`           |
| **Flashcard**     | Concept pair (front/back)       | `{ front, back, tags[] }`                                       |
| **Fill-in-blank** | Câu có chỗ trống + đáp án       | `{ template, blanks[], explanation }`                           |
| **Adventure Q&A** | Narrative + branching questions | `{ narrative, question, choices[], correct_path, consequence }` |
| **Matching**      | Pairs cần nối                   | `{ pairs[{left, right}], category }`                            |
| **True/False**    | Statement + boolean answer      | `{ statement, is_true, explanation }`                           |
| **Ordering**      | Items cần sắp xếp               | `{ items[], correct_order[], context }`                         |

MVP: **Quiz, Flashcard, Fill-in-blank** (đã validated). Thêm game types = thêm Pydantic schema + formatter prompt. Không cần thay đổi LangGraph graph.

### Edge Cases

- Tài liệu không có đủ content cho số câu yêu cầu → trả partial + warning
- Upload file không đúng format → 400 + supported formats list
- Vertex AI Search chưa index xong → 409 "Document still indexing"
- User query tài liệu của user khác → reject (scope enforcement)
- User chưa có docs + doc_scope="user" → 400 "No user documents found. Use doc_scope=system or all."
- System docs rỗng + doc_scope="system" → 400 "No system documents available"
- System docs rỗng + doc_scope="all" + user có docs → vẫn thành công (dùng user docs)
- PPTX chỉ có hình, ít text → warning "Insufficient text content"
- Code Execution timeout → retry simplified prompt, max 3 lần
- Câu hỏi trùng lặp → dedup check trong Formatter

## Success Criteria

**How will we know when we're done?**

### Functional

- [ ] Admin upload system docs → GCS `system/` folder → AI Search index thành công
- [ ] User upload personal docs → GCS `user/{user_id}/` folder → AI Search index thành công
- [ ] Generate với doc_scope="system" → chỉ dùng system docs
- [ ] Generate với doc_scope="user" → chỉ dùng user docs
- [ ] Generate với doc_scope="all" (default) → dùng cả hai, user-first (user docs xếp trước trong context)
- [ ] Generate không cần upload → dùng system docs → thành công
- [ ] User documents scoped: query chỉ trả kết quả từ tài liệu của user đó
- [ ] Generate request → JSON output hợp lệ cho 3 game types MVP
- [ ] Game template system: thêm game type mới không cần sửa graph
- [ ] JSON 100% conform Pydantic schema
- [ ] Reviewer reject → LangGraph feedback loop → retry → pass
- [ ] LangGraph checkpoint persistence hoạt động

### Quality

- [ ] Accuracy ≥ 98% trên bộ test 100 câu
- [ ] Grounded (bám sát tài liệu trong scope — user docs và/hoặc system docs — qua Vertex AI Search), không hallucinate
- [ ] Content items phù hợp với game type yêu cầu

### Performance

- [ ] < 60s cho 10 câu, < 5 phút cho 50 câu
- [ ] ≥ 10 concurrent requests trên Cloud Run
- [ ] Vertex AI Search query < 2s
- [ ] Document indexing < 15 phút cho file 50MB

### Cost

- [ ] ≤ $25/tháng tổng chi phí

## Constraints & Assumptions

**What limitations do we need to work within?**

### Technical Constraints

- **Cloud:** 100% GCP — project `green-mercury-485016-n1` (APIs đã enable, cần setup resources)
- **LLM:** Gemini Pro/Flash (Vertex AI)
- **Knowledge:** Vertex AI Search (Discovery Engine) — zero custom RAG
- **Orchestration:** LangGraph (core duy nhất cho business logic)
- **Runtime:** Python 3.12+, FastAPI, LangChain
- **Database:** Firestore (serverless, JSON-native)
- **Deploy:** Cloud Run
- **Input formats:** PDF, DOCX, PPTX

### Business Constraints

- Budget: ≤ $25/tháng
- Team: nhỏ, ưu tiên managed services
- Timeline: 4 tuần cho MVP

### Assumptions

- Vertex AI Search xử lý tốt PDF/DOCX/PPTX tiếng Việt
- Vertex AI Search hỗ trợ metadata filtering (scope per user)
- Gemini Code Execution hỗ trợ SymPy/NumPy
- `VertexAISearchRetriever` tích hợp được vào LangGraph
- Game Client team adapt JSON schema do AI service định nghĩa
- Output tiếng Việt, difficulty do AI tự xác định

### Privacy & Data Consent

- **User docs mặc định là riêng tư:** Chỉ user upload mới query được (scope enforcement qua metadata filter `user_id`).
- **System docs là tài liệu chung:** Tất cả users đều truy cập được. Admin chịu trách nhiệm chất lượng và bản quyền.
- **Consent policy:** Khi upload, user được yêu cầu đồng ý cho phép sử dụng tài liệu để cải thiện hệ thống (improve retrieval quality, prompt tuning).
  - **Đồng ý:** Tài liệu có thể được dùng để đánh giá và cải thiện chất lượng retrieval/generation (không training model).
  - **Không đồng ý:** Tài liệu chỉ được lưu GCS + index vào AI Search để phục vụ user đó. Không dùng cho mục đích khác.
- **Không dùng tài liệu user để training hoặc fine-tune model** (Gemini là API managed, không custom training).
- **Data retention:** Tài liệu user không hoạt động > 6 tháng → xem xét xóa. System docs (SGK, giáo trình) có tính lâu dài → không áp dụng auto-delete.
- **Phân loại tài liệu:** Hệ thống cần đánh giá tính chất tài liệu (lâu dài vs tạm thời) dựa trên metadata (subject, scope) để áp dụng retention policy phù hợp.

## Questions & Open Items

**What do we still need to clarify?**

### Đã quyết định

1. GCP project `green-mercury-485016-n1` — setup từ đầu
2. 100% GCP managed services
3. Vertex AI Search thay RAG pipeline
4. LangGraph = core duy nhất cho business logic
5. Firestore cho database (serverless)
6. JSON schema do AI service định nghĩa
7. GCS bucket: `user/{user_id}/{YYYY-MM-DD}/{session_id}/` — user isolation
8. GCS bucket: `system/{YYYY-MM-DD}/{session_id}/` — admin-managed shared docs
9. Input: PDF + DOCX + PPTX
10. All game types = Q&A-based, extensible template system
11. Tiếng Việt, sync API cho MVP
12. Dual doc sources: system docs (admin) + user docs (personal)

13. `doc_scope="all"` dùng user-first: query cả hai nguồn → post-retrieval re-ranking, user docs xếp trước system docs
14. Privacy & Data Consent: user đồng ý cho phép dùng tài liệu cải thiện hệ thống, không dùng để training model
15. User tiers (free/premium) = non-goal cho MVP, monitor usage trước
16. Data retention: user docs > 6 tháng không hoạt động → xem xét xóa. System docs (SGK) = lâu dài
17. Rate limiting: defer, tính sau khi có data usage thực tế
18. Max documents per user: chưa giới hạn, monitor usage → xem xét quota theo tier nếu cần
19. Vertex AI Search query quota: monitor usage, implement fallback/rate limit nếu vượt quota

### Cần validate qua PoC

20. Vertex AI Search + PDF/DOCX/PPTX tiếng Việt: chất lượng extractive answers
21. Vertex AI Search metadata filtering: scope query per user_id
22. Gemini Code Execution: thư viện sandbox hỗ trợ
23. Vertex AI Search pricing cho Data Store + query volume
24. `VertexAISearchRetriever` + metadata filter + LangGraph integration

### GCP APIs (đã enable)

Tất cả APIs đã được enable. Xem chi tiết resource setup tại Implementation Guide → GCP Setup section.

| API                              | Service          | Mục đích                      |
| -------------------------------- | ---------------- | ----------------------------- |
| `aiplatform.googleapis.com`      | Vertex AI        | Gemini Pro/Flash              |
| `discoveryengine.googleapis.com` | Vertex AI Search | Document indexing + retrieval |
| `run.googleapis.com`             | Cloud Run        | Deploy FastAPI                |
| `firestore.googleapis.com`       | Firestore        | Database                      |
| `storage.googleapis.com`         | Cloud Storage    | Document upload               |
| `secretmanager.googleapis.com`   | Secret Manager   | API keys                      |
| `cloudbuild.googleapis.com`      | Cloud Build      | CI/CD build                   |
| `logging.googleapis.com`         | Cloud Logging    | Structured logs               |
| `cloudtrace.googleapis.com`      | Cloud Trace      | Request tracing               |

### Future Roadmap (mở rộng LangGraph graph)

| Phase       | Focus                                                                            | LangGraph Node mới        | GCP Service thêm          |
| ----------- | -------------------------------------------------------------------------------- | ------------------------- | ------------------------- |
| **MVP**     | Q&A-based games (Quiz, Flashcard, Fill-blank) + Dual doc sources (System + User) | Content Agent + Formatter | Code Execution, AI Search |
| **Phase 2** | Narrative games (Adventure, Story-driven)                                        | Story Agent               | Context Caching           |
| **Phase 3** | Visual games (Image-based, Diagram)                                              | Visual Agent              | Gemini Vision             |
| **Phase 4** | Structured games (Table, Classification)                                         | Table Agent               | AI Search (structured)    |

---

> [!Note] Các quyết định từ User Note đã được tích hợp vào nội dung chính:
>
> - GCS bucket: `system/` (admin docs) + `user/{user_id}/` (user docs). Metadata AI Search: `user_id="__system__"` / `user_id="{user_id}"`.
> - APIs đã enable. Rate limit, retention, quota, privacy → đã ghi nhận trong "Đã quyết định" #13-19.
> - User tiers (free/premium) = non-goal cho MVP.
