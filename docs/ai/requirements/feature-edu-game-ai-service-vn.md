```markdown
---
phase: requirements
title: Tài liệu Yêu cầu
description: Định nghĩa vấn đề, mục tiêu, và phạm vi
---

# Yêu cầu: Edu Game AI Service

## Tóm tắt

**Chúng ta đang giải quyết vấn đề gì?**

Đội Game Client cần một AI service nội bộ có khả năng tạo nội dung game giáo dục (câu hỏi trắc nghiệm, flashcard, điền vào chỗ trống) dựa trên tài liệu do người dùng tải lên. Service cần đảm bảo độ chính xác cao (≥ 98%), đặc biệt cho các môn STEM đòi hỏi tính toán.

---

## Phát biểu Vấn đề

**Tại sao điều này lại quan trọng?**

Hiện tại, nội dung game giáo dục được tạo thủ công hoặc sử dụng ngân hàng câu hỏi tĩnh. Điều này gây ra:

1. **Tốn thời gian**: Tạo 50 câu hỏi chất lượng mất 2-4 giờ
2. **Không cá nhân hóa**: Nội dung không bám sát chương trình học/giáo án của giáo viên
3. **Khó scale**: Thêm môn/chủ đề mới đòi hỏi nỗ lực biên soạn đáng kể
4. **Sai sót nhiều**: Đặc biệt với các công thức toán/lý/hóa cần tính toán chính xác

---

## Mục tiêu và Phi-mục tiêu

**Chúng ta đang cố gắng đạt được điều gì?**

### Mục tiêu

- Tạo nội dung đa dạng (quiz, flashcard, fill-blank) từ tài liệu giáo dục (PDF, DOCX, PPTX)
- Đạt độ chính xác ≥ 98% với các câu hỏi số học (sử dụng Code Execution)
- Hỗ trợ multi-format input: PDF, DOCX, PPTX
- API JSON output phù hợp để Game Client gọi trực tiếp
- Multi-tenant với user scoping: mỗi user chỉ query được documents họ upload (trừ system docs)
- **System documents**: Admin có thể upload tài liệu chung (SGK, tài liệu tham khảo) cho tất cả users
- **User-first**: Khi generate với doc_scope="all", nội dung từ user docs được ưu tiên hiển thị trước system docs

### Phi-mục tiêu (Ngoài phạm vi hiện tại)

- Không tự host model (dùng Vertex AI)
- Không tạo hình ảnh/âm thanh (chỉ text)
- Không hỗ trợ real-time streaming
- Không quản lý user authentication (AI Service tin tưởng user_id từ upstream đã được xác thực)
- Chưa có Admin UI (admin sử dụng API trực tiếp)

### Chiến lược 4-Pillar

Hệ thống tuân theo **Chiến lược 4-Pillar** để xử lý tối ưu các loại nội dung giáo dục khác nhau:

| Cột trụ      | Loại dữ liệu            | Môn học                    | Thách thức                    | Giải pháp                              | Phase   |
| ------------ | ----------------------- | -------------------------- | ----------------------------- | -------------------------------------- | ------- |
| **Pillar 1** | Logic & Tính toán       | Toán, Lý, Hóa              | LLM tính sai                  | **Math Agent + Python Code Execution** | Phase 1 |
| **Pillar 2** | Tường thuật & Ngữ nghĩa | Văn, Sử, GDCD              | Mất context, quan hệ nhân quả | **Story Agent + GraphRAG**             | Phase 2 |
| **Pillar 3** | Không gian & Hình ảnh   | Địa, Sinh, Công nghệ       | Thông tin trong hình/sơ đồ    | **Visual Agent + Multimodal LLM**      | Phase 3 |
| **Pillar 4** | Cấu trúc & Taxonomy     | Ngữ pháp Anh, Bảng hóa học | Cấu trúc bảng/list bị vỡ      | **Structure Agent + Table Extraction** | Phase 4 |

Mỗi loại dữ liệu cần **xử lý chuyên biệt** — một agent chung không thể giải quyết tất cả vấn đề tối ưu.

---

## User Stories

**Ai sẽ sử dụng tính năng này và họ cần gì?**

### US-1: Giáo viên tạo quiz từ giáo án

> _Là một giáo viên, tôi muốn upload giáo án PDF và nhận về 10 câu trắc nghiệm phù hợp, để tiết kiệm thời gian soạn bài kiểm tra._

**Tiêu chí chấp nhận:**

- Giáo viên upload PDF lên GCS (thư mục `user/{user_id}/`)
- Gọi API với `game_type=quiz`, `num_questions=10`, `doc_scope="user"` hoặc `"all"` (default: "all")
- Response chứa 10 object QuizQuestion với 4 đáp án mỗi câu
- Câu hỏi bám sát nội dung tài liệu đã upload (không hallucinate)
- Nếu doc_scope="all", nội dung từ user docs xuất hiện trước system docs

### US-2: Học sinh ôn tập với flashcard

> _Là một học sinh, tôi muốn tạo flashcards từ bài giảng đã tải lên, để ôn tập kiến thức hiệu quả hơn._

**Tiêu chí chấp nhận:**

- Học sinh đã upload tài liệu (user docs)
- Gọi API với `game_type=flashcard`, `num_questions=20`, `doc_scope="user"`
- Response chứa 20 Flashcard với front/back text
- Front ngắn gọn (< 100 ký tự), back giải thích chi tiết

### US-3: Học sinh chưa upload, dùng SGK

> _Là một học sinh chưa upload tài liệu, tôi muốn tạo quiz từ SGK chung mà admin đã upload, để ôn tập theo chương trình chuẩn._

**Tiêu chí chấp nhận:**

- User chưa có docs riêng
- Gọi API với `game_type=quiz`, `num_questions=10`, `doc_scope="system"` (hoặc `"all"` sẽ fallback sang system)
- Response chứa quiz từ system docs (SGK, tài liệu tham khảo)
- Nội dung bám sát SGK, không hallucinate

### US-4: Admin upload SGK

> _Là admin, tôi muốn upload SGK và tài liệu tham khảo chung, để tất cả users đều có thể generate nội dung từ đó._

**Tiêu chí chấp nhận:**

- Admin gọi POST `/api/v1/admin/documents/upload` với file PDF/DOCX/PPTX (kèm scope: "system")
- File lưu vào GCS `system/` folder, metadata `user_id: "__system__"`
- AI Search index với filter `user_id: "__system__"`
- Tất cả user với doc_scope="system" hoặc "all" đều query được

### US-5: Game Client tích hợp API

> _Là developer Game Client, tôi muốn gọi AI API và nhận JSON chuẩn để render game trực tiếp._

**Tiêu chí chấp nhận:**

- API endpoint: `POST /api/v1/generate` với auth qua Cloud Run IAM
- Request body JSON với `user_id`, `topic`, `game_types[]`, `num_questions`, `doc_scope`
- Response schema cố định và documented
- Hỗ trợ batch generate (nhiều game type trong 1 request)
- Response <60s cho 10 câu (async via Cloud Tasks, client poll)

### US-6: Câu hỏi toán cần tính toán chính xác

> _Là người dùng, tôi muốn các câu hỏi toán/lý/hóa có đáp án chính xác, kể cả khi cần tính toán phức tạp._

**Tiêu chí chấp nhận:**

- AI sử dụng Code Execution để tính toán thay vì reasoning thuần
- Độ chính xác ≥ 98% trên test set 100 câu số học
- Sai số làm tròn được xử lý nhất quán (2 chữ số thập phân)

---

## Tiêu chí Chấp nhận

**Làm sao biết chúng ta đã hoàn thành?**

- [ ] API endpoint hoạt động, authn via Cloud Run IAM (chỉ upstream service gọi được)
- [ ] Hỗ trợ 3 game types: quiz, flashcard, fill_blank
- [ ] Hỗ trợ 3 file formats: PDF, DOCX, PPTX
- [ ] User scoping: mỗi user chỉ query được documents họ upload (trừ system docs)
- [ ] doc_scope parameter: "user" | "system" | "all" (default: "all")
- [ ] User-first: doc_scope="all" → user docs xuất hiện trước system docs
- [ ] Admin API: upload, list, delete system documents (stateless, không cần admin UI)
- [ ] Độ chính xác ≥ 98% trên golden test set
- [ ] Latency <60s cho 10 câu (p95, async + poll)
- [ ] Response schema đúng JSON documentation
- [ ] E2E test thành công với real Vertex AI + AI Search

---

## Ràng buộc Kỹ thuật

**Những giới hạn nào chúng ta cần làm việc trong đó?**

- **GCP-only stack**: Vertex AI, AI Search, Cloud Run, GCS, Firestore, Cloud Tasks
- **LangGraph**: Kiến trúc agent-based với human-in-the-loop ready
- **Python 3.12+**: Runtime chính
- **Không self-hosted models**: Chi phí và complexity không phù hợp Phase 1
- **Async-first**: Generation requests go through Cloud Tasks, client poll for results

---

## Ràng buộc Kinh doanh

**Những yếu tố kinh doanh nào ảnh hưởng đến quyết định?**

- **Timeline**: Phase 1 trong 2 tuần, toàn bộ 4 phases trong 8-9 tuần
- **Team**: 1 AI engineer, support từ Game Client team cho integration testing
- **Budget**: Giới hạn GCP credits cho giai đoạn khởi động (~$500/tháng)
- **Internal service**: Không có external customers, compliance đơn giản hơn
- **Data privacy**: User docs là private (scoped), system docs là shared cho tất cả. Cần minh bạch về data consent và không được sử dụng để train/fine-tune models.

---

## Phụ thuộc

**Chúng ta phụ thuộc vào những gì?**

- GCP Project: `green-mercury-485016-n1` (đã enable APIs)
- Game Client team: JSON schema agreement, integration testing
- Vertex AI Search: Data store setup, document indexing pipeline
- Cloud Tasks: Async job queue setup

---

## Các Câu hỏi Mở

**Những gì cần làm rõ thêm?**

- [ ] Số lượng concurrent users dự kiến? (Ước tính: 10-50 đồng thời)
- [ ] Error budget: chấp nhận bao nhiêu % request fail? (Target: <1%)
- [ ] Admin workflow chi tiết: ai là admin, flow approve documents?
- [ ] Retention policy: user docs giữ bao lâu? System docs giữ vĩnh viễn?
- [x] ~~Rate limiting: cần thiết không? Per-user limits?~~ → Không cần ở Phase 1 (internal service, trusted upstream đã limit)

---

## Quyền riêng tư & Đồng ý Dữ liệu

**Chúng ta xử lý dữ liệu người dùng như thế nào?**

### Quy tắc Nền tảng

- **User docs là private**: Chỉ user đã upload mới query được (via user_id filter)
- **System docs là shared**: Tất cả users có thể query (doc_scope="system" hoặc "all")
- **Không cross-user access**: User A không thể query docs của User B
- **User_id từ upstream là trusted**: AI Service không xác thực user, chỉ scope data theo user_id

### Đồng ý Dữ liệu

Dự kiến yêu cầu đồng ý từ upstream (Game Client hiển thị cho user):

> "Tài liệu bạn upload sẽ được lưu trữ và xử lý để tạo nội dung học tập. Dữ liệu không được chia sẻ với người dùng khác và không được sử dụng để huấn luyện AI models."

AI Service cần đảm bảo:

- [ ] Documents chỉ dùng cho RAG retrieval, không fine-tune
- [ ] Logs không chứa PII không cần thiết
- [ ] Metadata trong Firestore tối thiểu đủ dùng
- [ ] Deletion API cho phép user yêu cầu xóa docs (via upstream)
```
