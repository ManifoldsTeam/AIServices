---
phase: design
title: System Design & Architecture
description: Define the technical architecture, components, and data models
---

# System Design & Architecture

## Architecture Overview

**What is the high-level system structure?**

Kiến trúc 100% GCP Managed Services. **LangGraph** là core duy nhất cho business logic. **Vertex AI Search** thay thế hoàn toàn RAG pipeline. Hệ thống hỗ trợ **hai nguồn tài liệu**: system docs (Admin quản lý, luôn có sẵn) + user docs (cá nhân, optional). User có thể sinh game ngay mà không cần upload.

### Kiến trúc tổng quan

```mermaid
graph TD
    Admin[Admin] -->|Upload system docs| CloudRun
    User[User / Game Client] -->|REST API| CloudRun[Cloud Run<br/>FastAPI + LangGraph]

    subgraph "GCP Managed Services"
        GCS[(Cloud Storage<br/>system/ + user/user_id/)] -->|Auto-import| VAIS[Vertex AI Search<br/>Data Store + Metadata Filter]
        Firestore[(Firestore<br/>JSON Output + Metadata)]
        SecretMgr[Secret Manager]
    end

    subgraph "LangGraph Graph — Cloud Run"
        Supervisor{Supervisor Node<br/>Gemini Pro}

        Supervisor -->|Route| ContentAgent[Content Agent<br/>+ VertexAISearchRetriever<br/>filter: doc_scope<br/>+ Code Execution]

        ContentAgent --> Reviewer{Reviewer Node<br/>Gemini Flash}

        Reviewer -->|✅ Pass| Formatter[Formatter Node<br/>Game Template Transform<br/>Pydantic Structured Output]
        Reviewer -->|❌ Fail| Supervisor

        Formatter -->|Save| Firestore
    end

    CloudRun --> Supervisor
    ContentAgent -.->|Query docs<br/>system + user scoped| VAIS
    Formatter -->|JSON Response| User
```

### Thiết kế core

#### 1. LangGraph là trung tâm

Mọi business logic đều nằm trong LangGraph StateGraph:

- **Routing logic** = Supervisor node + conditional edges
- **Domain logic** = Specialized agent nodes (Content Agent cho MVP, thêm Story/Visual Agent sau)
- **Quality control** = Reviewer node + feedback loop edges
- **Output formatting** = Formatter node + Game Template system
- **State management** = LangGraph checkpoint (Firestore)

Mở rộng = thêm node + edge vào graph, không thay đổi core structure.

#### 2. Dual Document Sources

Hệ thống hỗ trợ hai nguồn tài liệu:

| Nguồn           | GCS prefix        | Ai quản lý | Metadata `user_id` |
| --------------- | ----------------- | ---------- | ------------------ |
| **System docs** | `system/`         | Admin      | `"__system__"`     |
| **User docs**   | `user/{user_id}/` | User       | `"{user_id}"`      |

```
GCS Bucket Structure:
gs://edu-game-docs-{project_id}/
├── system/                              # Admin-managed shared docs
│   ├── 2026-03-01/
│   │   └── {session_1}/
│   │       ├── sgk-toan-11.pdf
│   │       └── sgk-ly-12.pdf
│   └── 2026-03-03/
│       └── {session_2}/
│           └── sgk-hoa-10.pdf
├── user/                                # User personal docs
│   ├── {user_id}/
│   │   ├── 2026-03-03/
│   │   │   ├── {session_1}/
│   │   │   │   ├── giao-an-toan-11.pdf
│   │   │   │   └── slide-dao-ham.pptx
│   │   │   └── {session_2}/
│   │   │       └── giao-trinh-ly.docx
│   │   └── 2026-03-04/
│   │       └── ...
```

- **Admin upload:** GCS `system/{date}/{session}/` + metadata `user_id="__system__"`
- **User upload:** GCS `user/{user_id}/{date}/{session}/` + metadata `user_id="{user_id}"`
- **Query scoping (doc_scope):**
  - `"user"` → filter `user_id: ANY("{user_id}")`
  - `"system"` → filter `user_id: ANY("__system__")`
  - `"all"` (default) → filter `user_id: ANY("{user_id}", "__system__")` + **post-retrieval re-ranking: user docs xếp trước, system docs bổ sung** (user-first)
- → User A không thể truy cập tài liệu User B. User A có thể truy cập system docs.

#### 3. Flexible Game Template System

```
Content Agent sinh → Educational Content Items (generic Q&A)
                        ↓
Formatter nhận game_types[] → áp dụng Game Templates → output per type
```

Tất cả game types dựa trên Q&A foundation:

- **Content Items:** `{ question, answer, explanation, topic, difficulty, context_source }`
- **Game Template:** Pydantic schema + formatter prompt → transform content items → game-specific JSON
- Thêm game type = thêm 1 Pydantic model + 1 formatter prompt. Không sửa graph.

### Key Components

| Component              | Responsibility                                                                     | Model/Tech                                       |
| ---------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------ |
| **FastAPI Gateway**    | REST API, input validation, response                                               | FastAPI trên Cloud Run                           |
| **Supervisor Node**    | Phân tích request → routing sang agent phù hợp                                     | Gemini Pro                                       |
| **Content Agent Node** | Query Vertex AI Search (scoped by doc_scope) → sinh content items → Code Execution | Gemini Pro + Code Exec + VertexAISearchRetriever |
| **Reviewer Node**      | Kiểm tra chất lượng, grounding, accuracy                                           | Gemini Flash                                     |
| **Formatter Node**     | Transform content items → game-specific JSON via templates                         | Gemini Flash + Structured Output                 |
| **Vertex AI Search**   | Document indexing + semantic retrieval + metadata filtering                        | Discovery Engine Data Store                      |
| **Firestore**          | Lưu JSON output, metadata, generations, user info                                  | Firestore Native Mode                            |
| **Cloud Storage**      | User document storage (`user/{user_id}/`) + system docs (`system/`)                | GCS                                              |

### Technology Stack

| Layer          | Technology                                             | Rationale                                                               |
| -------------- | ------------------------------------------------------ | ----------------------------------------------------------------------- |
| Language       | Python 3.12+                                           | LangChain/LangGraph ecosystem                                           |
| API Framework  | FastAPI                                                | Async, type-safe, OpenAPI docs                                          |
| **Core Logic** | **LangGraph**                                          | **Stateful agent graph, feedback loop, checkpoint, extensible**         |
| LLM Framework  | LangChain Core                                         | Prompt templates, structured output, tool calling                       |
| LLM Provider   | Gemini Pro/Flash (Vertex AI)                           | Native agentic, code execution                                          |
| **Knowledge**  | **Vertex AI Search (Discovery Engine)**                | **Zero-code RAG: auto-index docs, semantic retrieval, metadata filter** |
| Retriever      | `VertexAISearchRetriever` (langchain-google-community) | LangChain-native, plugs into LangGraph                                  |
| Database       | Firestore                                              | Serverless, JSON-native, zero ops                                       |
| Object Storage | Cloud Storage                                          | Document upload: `system/` + `user/{user_id}/` folder isolation         |
| Deployment     | Cloud Run                                              | Serverless, auto-scale 0→N                                              |
| Secrets        | Secret Manager                                         | API keys, service account                                               |
| Monitoring     | Cloud Logging + Cloud Trace                            | Structured logs, request tracing                                        |

## Data Models

**What data do we need to manage?**

### Core Entities

#### GenerationRequest (API Input)

```python
class GenerationRequest(BaseModel):
    user_id: str                           # Required: scope docs per user
    document_ids: list[str] | None = None  # Optional: specific documents
    topic: str | None = None               # Chapter/topic to focus on
    game_types: list[GameType]             # QUIZ | FLASHCARD | FILL_BLANK | ...
    num_questions: int = 10
    difficulty: DifficultyLevel = "medium"  # easy | medium | hard
    doc_scope: DocScope = "all"            # "user" | "system" | "all"
    language: str = "vi"
```

#### GameType (Extensible Enum)

```python
class GameType(str, Enum):
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    FILL_BLANK = "fill_blank"
    ADVENTURE = "adventure"      # Phase 2
    MATCHING = "matching"        # Phase 2
    TRUE_FALSE = "true_false"    # Phase 2
    ORDERING = "ordering"        # Phase 2
```

#### Educational Content Item (Internal — Q&A foundation)

```python
class ContentItem(BaseModel):
    """Base educational content — Q&A at its core."""
    question: str
    answer: str
    explanation: str
    topic: str
    difficulty: DifficultyLevel
    context_source: str                    # Which doc/page the content is from
    doc_scope: str                         # "system" or "user" — tracks origin
    computation_trace: str | None = None   # Code execution trace if math
```

#### Game-Specific Output Schemas (Templates)

```python
# --- Quiz ---
class QuizQuestion(BaseModel):
    id: str
    question: str
    options: list[QuizOption]              # 4 options
    correct_answer_index: int              # 0-3
    explanation: str
    difficulty: DifficultyLevel
    topic: str
    computation_trace: str | None = None

class QuizOption(BaseModel):
    text: str
    is_correct: bool

# --- Flashcard ---
class Flashcard(BaseModel):
    id: str
    front: str                             # Concept / formula / question
    back: str                              # Explanation + example
    topic: str
    difficulty: DifficultyLevel
    tags: list[str] = []

# --- Fill-in-blank ---
class FillBlankQuestion(BaseModel):
    id: str
    template: str                          # "Fe + __ HCl → ..."
    blanks: list[BlankSlot]
    explanation: str
    difficulty: DifficultyLevel
    topic: str

class BlankSlot(BaseModel):
    position: int
    correct_answer: str
    hint: str | None = None

# --- Adventure Q&A (future) ---
class AdventureNode(BaseModel):
    id: str
    narrative: str                         # Story context
    question: str
    choices: list[AdventureChoice]
    correct_choice_index: int
    consequence: str                       # What happens next
    topic: str

class AdventureChoice(BaseModel):
    text: str
    is_correct: bool
    feedback: str

# --- Matching (future) ---
class MatchingGame(BaseModel):
    id: str
    pairs: list[MatchPair]
    category: str
    topic: str

class MatchPair(BaseModel):
    left: str
    right: str
```

#### Game Template Registry

```python
GAME_TEMPLATES: dict[GameType, type[BaseModel]] = {
    GameType.QUIZ: QuizQuestion,
    GameType.FLASHCARD: Flashcard,
    GameType.FILL_BLANK: FillBlankQuestion,
    GameType.ADVENTURE: AdventureNode,      # Phase 2
    GameType.MATCHING: MatchingGame,         # Phase 2
}
# Adding new game type = add entry here + define Pydantic model
```

#### Unified Response

```python
class GameContentResponse(BaseModel):
    request_id: str
    user_id: str
    generated_at: datetime
    content: dict[str, list[dict]]         # { "quiz": [...], "flashcard": [...] }
    metadata: GenerationMetadata

class GenerationMetadata(BaseModel):
    total_generated: int
    total_passed_review: int
    total_rejected: int
    generation_time_seconds: float
    model_used: str
    vertex_search_queries: int
    game_types_generated: list[str]
    cost_estimate_usd: float | None = None
```

#### Document Record (Firestore)

```python
class DocumentRecord(BaseModel):
    document_id: str
    user_id: str                           # "__system__" for admin docs
    filename: str
    file_format: str                       # pdf | docx | pptx
    gcs_uri: str
    upload_date: str                       # YYYY-MM-DD
    session_id: str
    index_status: str                      # uploading | indexing | ready | failed
    subject: str | None = None
    scope: str = "user"                    # "user" | "system"
    created_at: datetime
```

#### LangGraph State

```python
class AgentState(TypedDict):
    request: GenerationRequest
    doc_scope: str                         # "user" | "system" | "all"
    search_context: list[str]              # Retrieved from Vertex AI Search
    content_items: list[dict]              # Generated ContentItems (generic Q&A)
    reviewed_items: list[dict]             # After reviewer pass
    rejected_items: list[dict]             # Failed review
    iteration_count: int                   # For feedback loop max retry
    final_output: GameContentResponse | None
    errors: list[str]
```

### Data Flow

```mermaid
flowchart LR
    AdminDoc[Admin: PDF/DOCX/PPTX] -->|Upload| GCS_System["Cloud Storage<br/>system/{date}/{session}/"]
    UserDoc[User: PDF/DOCX/PPTX] -->|Upload| GCS_User["Cloud Storage<br/>user/{user_id}/{date}/{session}/"]
    GCS_System -->|Import + metadata| VAIS["Vertex AI Search<br/>Data Store"]
    GCS_User -->|Import + metadata| VAIS
    VAIS -->|"Retriever (filter: doc_scope)"| Agent[LangGraph<br/>Content Agent]
    Agent -->|Content Items| Formatter[Formatter<br/>Game Templates]
    Formatter -->|Game JSON| Firestore[(Firestore)]
    Firestore -->|API Response| Client[User / Game Client]
```

## API Design

**How do components communicate?**

### External REST API

#### POST /api/v1/documents/upload

Upload user document → GCS → trigger Vertex AI Search Data Store import.

```
Request: multipart/form-data {
  file: PDF/DOCX/PPTX,
  user_id: str,
  subject: str (optional)
}
Response: {
  document_id, user_id, filename, file_format,
  gcs_uri, index_status: "indexing", scope: "user"
}
```

#### POST /api/v1/admin/documents/upload

Admin upload system document → GCS `system/` → AI Search Data Store import.
Requires `X-Admin-Key` header.

```
Request: multipart/form-data {
  file: PDF/DOCX/PPTX,
  subject: str,
  grade: str (optional, e.g. "11")
}
Response: {
  document_id, user_id: "__system__", filename, file_format,
  gcs_uri, index_status: "indexing", scope: "system"
}
```

#### GET /api/v1/admin/documents

List all system documents. Requires `X-Admin-Key`.

```
Response: { documents: DocumentRecord[], total: int }
```

#### DELETE /api/v1/admin/documents/{document_id}

Delete a system document. Requires `X-Admin-Key`.

```
Response: { deleted: true }
```

#### GET /api/v1/documents/{document_id}/status

Check indexing status in Vertex AI Search.

```
Response: { document_id, index_status: "ready" | "indexing" | "failed" }
```

#### GET /api/v1/users/{user_id}/documents

List all documents for a user.

```
Response: { documents: DocumentRecord[], total: int }
```

#### POST /api/v1/generate

Sinh nội dung game. Core endpoint. `doc_scope` quyết định nguồn tài liệu.

```
Request: GenerationRequest (JSON) — includes doc_scope: "user" | "system" | "all"
Response: GameContentResponse (JSON)
```

#### GET /api/v1/generations/{request_id}

Lấy kết quả generation đã lưu.

```
Response: GameContentResponse (JSON)
```

#### GET /api/v1/game-types

List available game types + their schemas.

```
Response: { game_types: [{ type, description, schema_example }] }
```

### Authentication

- MVP: API Key qua header `X-API-Key` + `X-User-Id` header
- Admin endpoints: `X-Admin-Key` header (separate key, stored in Secret Manager)
- Future: OAuth2/JWT khi multi-tenancy

### Internal: LangGraph ↔ GCP Services

- **LangGraph → Vertex AI Search:** qua `VertexAISearchRetriever` + metadata filter (doc_scope-aware)
- **LangGraph → Gemini:** qua `ChatVertexAI` (langchain-google-vertexai)
- **LangGraph → Firestore:** qua `google-cloud-firestore` SDK
- **LangGraph Checkpoint:** Firestore hoặc custom async checkpointer

## Component Breakdown

**What are the major building blocks?**

### Source Code Structure

```
src/
├── api/                        # FastAPI layer
│   ├── routes/
│   │   ├── documents.py        # User upload, list, status
│   │   ├── admin.py            # Admin upload/list/delete system docs
│   │   ├── generate.py         # Generate game content
│   │   └── game_types.py       # List available game types
│   ├── schemas/                # Pydantic request/response
│   │   ├── requests.py
│   │   ├── responses.py
│   │   └── game_content.py     # All game type schemas
│   └── deps.py                 # API key auth, admin key auth, user_id extraction
├── graph/                      # LangGraph — ALL business logic
│   ├── builder.py              # StateGraph definition & compile
│   ├── state.py                # AgentState TypedDict
│   └── nodes/
│       ├── supervisor.py       # Routing logic
│       ├── content_agent.py    # Query AI Search + generate content items + Code Exec
│       ├── reviewer.py         # Quality check (Gemini Flash)
│       └── formatter.py        # Game template transform (Pydantic structured output)
├── templates/                  # Game type templates
│   ├── registry.py             # GAME_TEMPLATES dict
│   ├── quiz.py                 # Quiz schema + formatter prompt
│   ├── flashcard.py            # Flashcard schema + formatter prompt
│   └── fill_blank.py           # Fill-in-blank schema + formatter prompt
├── services/                   # GCP service wrappers (stateless)
│   ├── vertex_search.py        # VertexAISearchRetriever factory + doc_scope filter + user-first re-ranking
│   ├── llm.py                  # ChatVertexAI Pro/Flash factory
│   ├── document_store.py       # GCS upload (system/ + user/{user_id}/) + AI Search import
│   └── firestore.py            # Firestore CRUD
├── config/
│   └── settings.py             # Pydantic BaseSettings
└── main.py                     # FastAPI app init
```

### Key Design: `graph/` is the brain, `templates/` is the vocabulary

- `graph/builder.py` — defines the full `StateGraph`: nodes, edges, conditional routing, feedback loop
- `graph/nodes/*` — each node is a self-contained function that reads/writes `AgentState`
- `templates/*` — each game type has a schema (Pydantic) + formatter prompt
- Adding new agent = new file in `nodes/` + register in `builder.py`
- Adding new game type = new file in `templates/` + register in `registry.py`

## Design Decisions

**Why did we choose this approach?**

### DD-1: Vertex AI Search thay RAG pipeline tự build

- **Quyết định:** Vertex AI Search (Discovery Engine) Data Store làm knowledge retrieval.
- **Lý do:** Zero code indexing/chunking/embedding. Upload docs → auto-index → query qua `VertexAISearchRetriever`. Team không có infra → managed service.
- **Trade-off:** Phụ thuộc GCP pricing. Ít control hơn custom RAG. Nhưng cho MVP, tốc độ >> customization.

### DD-2: LangGraph là core logic duy nhất

- **Quyết định:** Mọi business logic nằm trong LangGraph StateGraph.
- **Lý do:** Extensible — thêm agent = thêm node. Feedback loop = conditional edge. Checkpoint = state persistence.
- **Trade-off:** Learning curve LangGraph, nhưng investment xứng đáng cho multi-agent roadmap.

### DD-3: Firestore thay PostgreSQL cho MVP

- **Quyết định:** Firestore Native Mode cho database.
- **Lý do:** Serverless, JSON-native, free tier generous. Cloud SQL cần provisioning.
- **Trade-off:** Không có SQL query. Nhưng MVP chỉ cần key-value CRUD cho JSON content.

### DD-4: Gemini Flash cho Reviewer & Formatter

- **Quyết định:** Gemini Flash cho review + formatting. Pro chỉ cho Supervisor + Content Agent.
- **Lý do:** Reviewer check logic đơn giản. Formatter chỉ reformat. Tiết kiệm 90%+ cost.

### DD-5: GCS folder structure cho document isolation

- **Quyết định:** `system/{YYYY-MM-DD}/{session_id}/` cho admin docs, `user/{user_id}/{YYYY-MM-DD}/{session_id}/` cho user docs.
- **Lý do:** Cùng bucket, cùng Data Store. GCS path rõ ràng (`system/` vs `user/`). Phân biệt qua metadata `user_id` trong AI Search (`__system__` vs real user_id).
- **Trade-off:** Cần đảm bảo metadata filter hoạt động chính xác với `ANY()` filter cho multi-value. Validate qua PoC.

### DD-6: Game Template system thay hardcoded game types

- **Quyết định:** Content Agent sinh generic content items → Formatter transform via game templates.
- **Lý do:** Extensible. Thêm game type = thêm schema + prompt. Không thay đổi LangGraph graph, không thay đổi Content Agent logic.
- **Trade-off:** Extra abstraction layer. Nhưng payoff lớn khi roadmap có 7+ game types.

### DD-7: Sync API → Async future

- **Quyết định:** Sync request-response cho MVP.
- **Lý do:** Simple. 10 câu < 60s chấp nhận được. Future: Cloud Tasks/Pub-Sub cho async batch.

### DD-8: Dual document sources (system + user)

- **Quyết định:** System docs (Admin) + User docs (cá nhân) cùng tồn tại trong 1 Data Store. `doc_scope` param quyết định nguồn query. `doc_scope="all"` dùng **user-first**: query cả hai nguồn, post-retrieval re-ranking với user docs xếp trước.
- **Lý do:** Hệ thống cần có data sẵn trước khi user upload. Admin cung cấp SGK/giáo trình chuẩn. User có thể sinh game ngay không cần upload. Nếu user có docs riêng, ưu tiên docs đó.
- **Trade-off:** Cùng Data Store → metadata filter phải chính xác. Re-ranking thêm 1 bước post-processing nhưng đảm bảo user-first. Admin key riêng với user API key.

## Non-Functional Requirements

**How should the system perform?**

### Performance

- 10 câu < 60s, 50 câu < 5 phút
- Concurrent: ≥ 10 requests (Cloud Run auto-scale)
- Vertex AI Search query: < 2s
- Document indexing: < 15 phút cho 50MB file

### Scalability

- Cloud Run: auto-scale 0→N instances
- Vertex AI Search: managed, scalable
- Firestore: auto-scale reads/writes
- GCS: unlimited storage per user
- Stateless API (state in Firestore + LangGraph checkpoint)

### Security

- API Key auth (Secret Manager) + user_id scoping + admin key for system docs
- Document isolation: user_id metadata filtering in AI Search. System docs accessible to all users.
- **Privacy:** User docs riêng tư (scoped). System docs chung. Consent policy khi upload (xem Requirements → Privacy & Data Consent).
- File upload: 50MB limit, PDF/DOCX/PPTX only (magic bytes check)
- GCS: uniform bucket-level access
- Cloud Run: IAM-controlled invocation
- No PII in generated content

### Reliability

- LangGraph checkpoint: resume from last node on crash
- Retry logic: exponential backoff cho Gemini/AI Search API calls
- Max 3 feedback loop iterations (prevent infinite loop)
- Cloud Run SLA: 99.95%

### Observability

- Structured JSON logging → Cloud Logging
- Request tracing → Cloud Trace
- Metrics: generation latency, success rate, token usage, AI Search queries, cost/request
- Per-user metrics: documents uploaded, generations count
- Alert: error rate > 5%, p95 latency > 120s
