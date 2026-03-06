---
phase: design
title: Phân tích Rủi ro và Trade-offs
description: Đánh giá rủi ro và trade-offs cho từng quyết định thiết kế
---

# Phân tích Rủi ro và Trade-offs: Edu Game AI Service

## Mục lục

1. [Xác thực: Cloud Run IAM Service-to-Service](#1-xác-thực-cloud-run-iam-service-to-service)
2. [Async Generation via Cloud Tasks](#2-async-generation-via-cloud-tasks)
3. [Chiến lược Dữ liệu: Doc Scope + User-first](#3-chiến-lược-dữ-liệu-doc-scope--user-first)
4. [Công nghệ Cốt lõi: Vertex AI + LangGraph](#4-công-nghệ-cốt-lõi-vertex-ai--langgraph)
5. [Chi phí & Tối ưu](#5-chi-phí--tối-ưu)
6. [Khả năng Mở rộng & Vendor Lock-in](#6-khả-năng-mở-rộng--vendor-lock-in)
7. [Quyền riêng tư & Bảo mật](#7-quyền-riêng-tư--bảo-mật)
8. [Khả năng Phục hồi Lỗi](#8-khả-năng-phục-hồi-lỗi)
9. [Khả năng Quan sát (Observability)](#9-khả-năng-quan-sát-observability)
10. [Tóm tắt Quyết định](#10-tóm-tắt-quyết-định)

---

## 1. Xác thực: Cloud Run IAM Service-to-Service

### Quyết định

Sử dụng Cloud Run IAM native thay vì API key, custom JWT, hoặc gateway auth.

### Trade-offs

| Khía cạnh            | Cloud Run IAM ✅                            | API Key / JWT                                   |
| -------------------- | ------------------------------------------- | ----------------------------------------------- |
| **Độ phức tạp code** | Zero—GCP xử lý tự động                      | Cần middleware xác minh, xử lý token hết hạn    |
| **Bảo mật**          | GCP-managed, audit sẵn có, IAM granular     | Tự quản lý rotation, lưu vault                  |
| **Flexibility**      | Chỉ GCP services hoặc SAs có thể gọi        | Bất kỳ client nào có key đều gọi được           |
| **Debugging**        | Cần hiểu IAM; lỗi 403 không rõ ràng ban đầu | Lỗi rõ ràng hơn (token hết hạn, key sai)        |
| **Vendor lock-in**   | Cao—phụ thuộc GCP IAM hoàn toàn             | Portable—có thể migrate key/JWT sang cloud khác |
| **Audit**            | Cloud Audit Logs tự động                    | Phải tự log                                     |

### Rủi ro & Giảm thiểu

| Rủi ro                                    | Khả năng   | Tác động   | Giảm thiểu                                         |
| ----------------------------------------- | ---------- | ---------- | -------------------------------------------------- |
| Cấu hình IAM sai → 403 blocking           | Trung bình | Cao        | Checklist setup, integration test trước triển khai |
| Không hiểu IAM → debug khó                | Trung bình | Trung bình | Document rõ ràng quy trình IAM grant               |
| GCP IAM outage → service unreachable      | Thấp       | Cao        | Chấp nhận—GCP SLA 99.95%                           |
| Migrate sang cloud khác cần viết lại auth | Thấp (MVP) | Cao        | Nếu cần, tách auth middleware layer sau            |

### Kết luận

**Chấp nhận** Cloud Run IAM cho MVP. Lợi ích zero-code auth và GCP-managed security vượt trội hơn lock-in risk cho internal service. Nếu cần multi-cloud sau, tách auth layer.

---

## 2. Async Generation via Cloud Tasks

### Quyết định

POST /generate trả về 202 + request_id ngay lập tức. Xử lý qua Cloud Tasks. Client poll GET /generations/{id} để lấy kết quả.

### Trade-offs

| Khía cạnh          | Async + Cloud Tasks ✅                     | Sync API                                  |
| ------------------ | ------------------------------------------ | ----------------------------------------- |
| **Latency UX**     | Client không bị block, poll khi cần        | Client block chờ response, có thể timeout |
| **Reliability**    | Retry tự động, dead-letter queue           | Timeout = fail, client phải retry         |
| **Complexity**     | Cần implement polling, job status tracking | Đơn giản hơn—1 request 1 response         |
| **Scalability**    | Decouple request rate vs processing rate   | Coupled—request spike = overload          |
| **Error handling** | Structured: pending → completed/failed     | Timeout hay 5xx đều giống nhau            |
| **Cost**           | Cloud Tasks có cost nhỏ                    | Không có thêm cost                        |

### Rủi ro & Giảm thiểu

| Rủi ro                                   | Khả năng   | Tác động   | Giảm thiểu                                          |
| ---------------------------------------- | ---------- | ---------- | --------------------------------------------------- |
| Client implement polling sai → UX kém    | Trung bình | Trung bình | Cung cấp SDK/example, document rõ polling interval  |
| Cloud Tasks queue backlog → latency tăng | Trung bình | Trung bình | Monitor queue depth, tune max-concurrent-dispatches |
| Job stuck ở processing vĩnh viễn         | Thấp       | Cao        | TTL cho job status, timeout task sau 5 phút         |
| Internal endpoint bị gọi trực tiếp       | Thấp       | Cao        | Verify X-CloudTasks-TaskName header                 |

### Kết luận

**Chấp nhận** async pattern. Generation có thể mất 30-60s, sync API sẽ gặp timeout problems. Cloud Tasks cung cấp retry và reliability miễn phí. Client polling complexity là cần thiết cho production-quality UX.

---

## 3. Chiến lược Dữ liệu: Doc Scope + User-first

### Quyết định

- 3 doc_scope options: `"user"` | `"system"` | `"all"` (default: "all")
- GCS paths: `system/` cho admin docs, `user/{user_id}/` cho user docs
- AI Search filter: metadata `user_id` với `__system__` cho shared docs
- User-first re-ranking: khi doc_scope="all", user docs xếp trước system docs

### Trade-offs

| Khía cạnh           | 3 Scopes + User-first ✅                    | Chỉ có All                                 |
| ------------------- | ------------------------------------------- | ------------------------------------------ |
| **Flexibility UX**  | User chọn scope tùy context                 | Đơn giản nhưng không kiểm soát được source |
| **Personalization** | User docs ưu tiên → content cá nhân hóa hơn | Mix có thể dilute nội dung cá nhân         |
| **Complexity**      | 3 code paths, query filter khác nhau        | 1 code path, 1 filter                      |
| **Testing**         | 3x test cases cho scoping                   | Ít test cases hơn                          |
| **Onboarding**      | User chưa có docs vẫn dùng được (system)    | Tương tự                                   |

### Rủi ro & Giảm thiểu

| Rủi ro                                       | Khả năng   | Tác động   | Giảm thiểu                                         |
| -------------------------------------------- | ---------- | ---------- | -------------------------------------------------- |
| User nhầm lẫn doc_scope → unexpected results | Trung bình | Thấp       | Default "all" hợp lý nhất, document rõ behavior    |
| Re-ranking overhead cho large result sets    | Thấp       | Thấp       | max_documents ~5-10, O(n) sort không đáng kể       |
| Metadata filter bypass → cross-user access   | Thấp       | Cao        | Test kỹ filter logic, không expose raw query param |
| System docs overpower user docs trong "all"  | Trung bình | Trung bình | User-first re-ranking giải quyết vấn đề này        |

### Kết luận

**Chấp nhận** 3 scopes + user-first. Flexibility quan trọng cho UX—user có thể chỉ muốn nội dung từ tài liệu của họ, hoặc ngược lại. User-first đảm bảo personalization khi dùng "all".

---

## 4. Công nghệ Cốt lõi: Vertex AI + LangGraph

### Quyết định

- **LLM**: Vertex AI Gemini (Pro cho generation, Flash cho review/format)
- **Orchestration**: LangGraph StateGraph với feedback loop
- **RAG**: Vertex AI Search (Agent Builder) + VertexAISearchRetriever
- **Code Execution**: Native Gemini Code Execution tool

### Trade-offs so với Alternatives

| Khía cạnh            | Vertex AI + LangGraph ✅                      | OpenAI + LangChain thuần                  | Self-hosted LLM                         |
| -------------------- | --------------------------------------------- | ----------------------------------------- | --------------------------------------- |
| **Cost per request** | Gemini pricing (~$0.001-0.002/request)        | GPT-4 pricing (~$0.01-0.03/request)       | Fixed infra cost, amortized per request |
| **Latency**          | 1-2s/query (AI Search) + 30-50s (generation)  | Tương tự hoặc chậm hơn                    | Có thể nhanh hơn nếu optimized          |
| **Accuracy (STEM)**  | Gemini Code Execution rất tốt                 | Code Interpreter cũng tốt                 | Phụ thuộc model quality                 |
| **Maintenance**      | Managed—không cần maintain model/search infra | Managed LLM, nhưng cần tự build vector DB | Cao—cần DevOps, GPU, scaling            |
| **GCP Integration**  | Native—IAM, logging, tracing                  | Cần thêm integration work                 | Cần tự build tất cả                     |
| **Lock-in**          | Cao—GCP specific                              | Trung bình—OpenAI but portable            | Thấp—self-hosted                        |

### Rủi ro & Giảm thiểu

| Rủi ro                                       | Khả năng   | Tác động   | Giảm thiểu                                         |
| -------------------------------------------- | ---------- | ---------- | -------------------------------------------------- |
| Gemini model quality không đủ cho tiếng Việt | Thấp       | Cao        | Test kỹ với Vietnamese content, có fallback prompt |
| Vertex AI Search indexing chậm/fail          | Trung bình | Trung bình | Monitor indexing status, retry mechanism           |
| LangGraph complexity → bugs khó debug        | Trung bình | Trung bình | Comprehensive logging, LangSmith tracing           |
| API pricing tăng đột ngột                    | Thấp       | Trung bình | Monitor cost, alert trên budget threshold          |
| Code Execution timeout/fail cho complex math | Trung bình | Trung bình | Simplify prompt, retry với smaller scope           |

### Kết luận

**Chấp nhận** Vertex AI + LangGraph stack. GCP-native integration, managed services, và Gemini quality đủ tốt cho MVP. Lock-in là acceptable cho internal service.

---

## 5. Chi phí & Tối ưu

### Ước tính Chi phí MVP (Monthly)

Giả định: 1000 generation requests/tháng, 10 questions mỗi request.

| Component            | Đơn giá ước tính                              | Monthly Cost (1000 reqs) |
| -------------------- | --------------------------------------------- | ------------------------ |
| **Gemini Pro**       | $0.00125/1K chars input, $0.00375/1K output   | ~$50                     |
| **Gemini Flash**     | $0.000125/1K chars input, $0.000375/1K output | ~$10                     |
| **Vertex AI Search** | $2.5/1000 queries                             | ~$5 (2 queries/req)      |
| **Cloud Storage**    | $0.02/GB/month                                | ~$2 (đủ cho 100GB docs)  |
| **Firestore**        | $0.18/100K reads, $0.18/100K writes           | ~$5                      |
| **Cloud Run**        | $0.00002400/vCPU-second                       | ~$20                     |
| **Cloud Tasks**      | $0.40/million tasks                           | ~$1                      |
| **Tổng ước tính**    |                                               | **~$93/tháng**           |

### Chiến lược Tối ưu

| Chiến lược                                 | Tiết kiệm ước tính | Trade-off                  |
| ------------------------------------------ | ------------------ | -------------------------- |
| Dùng Gemini Flash thay Pro cho generation  | -30%               | Có thể giảm quality nhẹ    |
| Cache AI Search results (same query in 1h) | -20% AI Search     | Stale results nếu docs mới |
| Batch multiple questions trong 1 LLM call  | -15%               | Tăng prompt complexity     |
| Limit num_questions per request            | Linh hoạt          | UX constraint              |

### Kết luận

~$93/tháng (ước tính thô) nằm trong budget $500/tháng. Buffer đủ cho spike và testing. Monitor cost weekly để adjust nếu cần.

---

## 6. Khả năng Mở rộng & Vendor Lock-in

### Đánh giá Lock-in

| Component            | Mức độ Lock-in | Effort để Replace                                       |
| -------------------- | -------------- | ------------------------------------------------------- |
| **Vertex AI (LLM)**  | Trung bình     | Swap ChatVertexAI → ChatOpenAI/ChatAnthropic (1-2 ngày) |
| **Vertex AI Search** | Cao            | Build vector DB + embedding pipeline (1-2 tuần)         |
| **Cloud Run**        | Thấp           | Containerized—deploy sang AWS ECS/Azure ACI dễ dàng     |
| **Firestore**        | Trung bình     | Switch sang MongoDB/DynamoDB (data migration 2-3 ngày)  |
| **Cloud Storage**    | Thấp           | S3/Azure Blob tương đương                               |
| **Cloud Tasks**      | Trung bình     | Replace với AWS SQS hoặc self-hosted queue (3-5 ngày)   |
| **Cloud Run IAM**    | Cao            | Cần implement auth layer riêng (3-5 ngày)               |

### Chiến lược Giảm Lock-in (Nếu cần sau)

1. **Abstract service interfaces**: Wrapper classes cho GCS, Firestore, LLM
2. **Config-driven**: Model selection, bucket names từ env vars
3. **Portable logging**: Structured JSON logs compatible với nhiều platforms

### Kết luận

Lock-in chấp nhận được cho MVP. Tổng effort migrate ~2-3 tuần nếu thực sự cần. Focus MVP delivery trước, refactor for portability nếu có demand.

---

## 7. Quyền riêng tư & Bảo mật

### Threat Model (Simplified)

| Threat                              | Khả năng   | Tác động   | Giảm thiểu                                    |
| ----------------------------------- | ---------- | ---------- | --------------------------------------------- |
| Cross-user document access          | Thấp       | Cao        | AI Search metadata filter + test kỹ           |
| Malicious document upload (malware) | Thấp       | Trung bình | File type validation, size limit, GCS scan    |
| PII leakage trong logs              | Trung bình | Trung bình | Log chỉ IDs, không log full content           |
| LLM prompt injection via document   | Trung bình | Trung bình | Sanitize retrieval results, output validation |
| Unauthorized service access         | Thấp       | Cao        | Cloud Run IAM—chỉ upstream service có quyền   |
| Internal endpoint bypass            | Thấp       | Cao        | Verify X-CloudTasks header cho /internal/\*   |

### Yêu cầu Compliance cho MVP

- Không có PII regulations (internal service, không external users trực tiếp)
- Data consent: upstream hiển thị thông báo cho user, AI Service không train trên docs
- Data retention: User có thể yêu cầu xóa (via upstream)

### Kết luận

Security posture phù hợp cho internal service. Cloud Run IAM + metadata isolation là đủ cho MVP. Monitor cho production rollout rộng hơn.

---

## 8. Khả năng Phục hồi Lỗi

### Failure Scenarios & Recovery

| Scenario                   | Recovery Strategy                                               |
| -------------------------- | --------------------------------------------------------------- |
| Gemini API 500/timeout     | Retry 3x với exponential backoff (1s, 2s, 4s) trong Cloud Tasks |
| AI Search no results       | Retry với rephrased query, sau đó trả 400 với message rõ        |
| Document indexing failed   | Mark indexing_status="failed", notify user, allow re-upload     |
| Firestore unavailable      | Fail fast với 503, rely on Cloud Tasks retry                    |
| Cloud Run instance crash   | Auto-restart, stateless design                                  |
| Cloud Tasks queue overload | Backpressure via max-concurrent-dispatches config               |
| Job stuck in "processing"  | TTL 10 phút, mark failed nếu không complete                     |

### Recovery Testing Checklist

- [ ] Simulate Gemini timeout → verify retry
- [ ] Simulate AI Search empty → verify rephrased query
- [ ] Simulate Cloud Tasks failure → verify dead-letter handling
- [ ] Simulate Firestore outage → verify 503 response
- [ ] Simulate long-running job → verify TTL timeout

### Kết luận

Cloud Tasks + retry strategy cung cấp resilience tốt. Stateless Cloud Run design cho phép fast recovery. Test failure scenarios trước production.

---

## 9. Khả năng Quan sát (Observability)

### Logging Strategy

| Level   | Nội dung log                                        |
| ------- | --------------------------------------------------- |
| INFO    | Request received, job created, job completed        |
| DEBUG   | LangGraph node transitions, retrieval results count |
| WARNING | Retry triggered, partial results returned           |
| ERROR   | API failures, validation errors, job failed         |

### Metrics to Track

| Metric                            | Alert Threshold           |
| --------------------------------- | ------------------------- |
| Request latency (p95)             | > 90s → alert             |
| Error rate                        | > 2% → alert              |
| AI Search query count per request | > 5 → investigate         |
| Gemini token usage per request    | > 10K tokens → cost alert |
| Cloud Tasks queue depth           | > 100 → scale alert       |
| Job completion rate               | < 95% → investigate       |

### Tracing

- LangGraph: LangSmith integration (optional, nếu cost cho phép)
- GCP: Cloud Trace cho E2E request tracing
- Structured logs với `request_id` để correlate

### Kết luận

Structured logging + Cloud Trace đủ cho MVP. LangSmith nice-to-have nếu debugging complexity cao. Set up alerts trước production launch.

---

## 10. Tóm tắt Quyết định

### Quyết định Đã Đưa Ra

| #   | Quyết định                  | Trạng thái   | Rủi ro Chính                      | Giảm thiểu                           |
| --- | --------------------------- | ------------ | --------------------------------- | ------------------------------------ |
| D1  | Cloud Run IAM auth          | ✅ Chấp nhận | Lock-in, IAM config sai           | Document quy trình, integration test |
| D2  | Async via Cloud Tasks       | ✅ Chấp nhận | Polling complexity, job stuck     | SDK/example, TTL timeout             |
| D3  | 3 doc_scope options         | ✅ Chấp nhận | User confusion, filter bypass     | Default "all", test kỹ               |
| D4  | User-first re-ranking       | ✅ Chấp nhận | Overhead (nhỏ)                    | Limit max_documents                  |
| D5  | Vertex AI + LangGraph stack | ✅ Chấp nhận | Lock-in, cost, Vietnamese quality | Monitor cost, test tiếng Việt        |
| D6  | GCS path separation         | ✅ Chấp nhận | Sync path với metadata            | Document structure rõ                |
| D7  | Trusted user_id từ upstream | ✅ Chấp nhận | Phụ thuộc upstream security       | Internal service trust model         |

### Rủi ro còn lại cần theo dõi

1. **Gemini tiếng Việt quality** — Cần golden test với Vietnamese content
2. **AI Search indexing speed** — Monitor initial deployment
3. **Cost growth** — Weekly cost review, alert nếu vượt budget
4. **Cloud Tasks queue health** — Monitor latency và backlog

### Điều kiện tiên quyết trước Production

- [ ] IAM setup tested end-to-end (upstream → AI Service)
- [ ] Async flow tested (POST → poll → completed)
- [ ] Vietnamese content accuracy validated (≥ 98% golden test)
- [ ] Cost monitoring alerts configured
- [ ] Failure recovery scenarios tested
- [ ] Logging và tracing verified trong Cloud Console
