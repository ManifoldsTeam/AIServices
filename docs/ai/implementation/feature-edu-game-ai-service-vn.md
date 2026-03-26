````markdown
---
phase: implementation
title: Hướng dẫn Triển khai
description: Ghi chú triển khai kỹ thuật, patterns, và hướng dẫn code
---

# Hướng dẫn Triển khai

## Thiết lập Môi trường Phát triển

**Làm sao để bắt đầu?**

### Yêu cầu Tiên quyết

- Python 3.12+
- Docker & Docker Compose
- `gcloud` CLI đã cài đặt và xác thực
- `uv` để quản lý dependencies

### Thiết lập GCP Project (Enable APIs → Setup Resources)

Project `green-mercury-485016-n1` đã **enable tất cả APIs cần thiết**. Chạy setup bên dưới để tạo resources trước khi bắt đầu code.

#### Bước 1: Xác thực và set project

```bash
gcloud auth login
gcloud config set project green-mercury-485016-n1
gcloud auth application-default login

# Xác minh
gcloud config list
```
````

#### Bước 2: Enable TẤT CẢ APIs cần thiết

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudtasks.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com

# Xác minh (nên thấy ít nhất 10 APIs)
gcloud services list --enabled --filter="config.name:googleapis.com" | wc -l
```

#### Bước 3: Tạo Cloud Storage bucket

```bash
# Bucket cho upload tài liệu (system + user)
gsutil mb -b on -l asia-southeast1 \
  gs://edu-game-docs-green-mercury-485016-n1

# Test: tạo cấu trúc thư mục
# System docs
echo "test" | gsutil cp - \
  gs://edu-game-docs-green-mercury-485016-n1/system/2026-03-03/session-1/test.txt
# User docs
echo "test" | gsutil cp - \
  gs://edu-game-docs-green-mercury-485016-n1/user/test-user/2026-03-03/session-1/test.txt

gsutil ls gs://edu-game-docs-green-mercury-485016-n1/system/
gsutil ls gs://edu-game-docs-green-mercury-485016-n1/user/test-user/

# Cleanup file test
gsutil rm gs://edu-game-docs-green-mercury-485016-n1/system/2026-03-03/session-1/test.txt
gsutil rm gs://edu-game-docs-green-mercury-485016-n1/user/test-user/2026-03-03/session-1/test.txt
```

#### Bước 4: Tạo Firestore database

```bash
gcloud firestore databases create --location=asia-southeast1

# Xác minh
gcloud firestore databases list
```

#### Bước 5: Tạo Vertex AI Search Data Store

Qua GCP Console (khuyến nghị cho setup lần đầu):

1. Vào **Agent Builder** → **Data Stores** → **Create**
2. Source: **Cloud Storage**
3. Chọn bucket: `edu-game-docs-green-mercury-485016-n1`
4. Data type: **Unstructured documents**
5. Name: `edu-game-docs`
6. Create → ghi chú `DATA_STORE_ID`

Hoặc qua REST API:

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1/projects/green-mercury-485016-n1/locations/global/collections/default_collection/dataStores?dataStoreId=edu-game-docs" \
  -d '{
    "displayName": "edu-game-docs",
    "industryVertical": "GENERIC",
    "contentConfig": "CONTENT_REQUIRED",
    "solutionTypes": ["SOLUTION_TYPE_SEARCH"]
  }'
```

Sau đó tạo Search App:

1. Agent Builder → **Apps** → **Create**
2. Type: **Search** → Generic
3. Link tới `edu-game-docs` Data Store

#### Bước 6: Tạo Service Account

```bash
gcloud iam service-accounts create edu-game-ai \
  --display-name="Edu Game AI Service"

SA_EMAIL=edu-game-ai@green-mercury-485016-n1.iam.gserviceaccount.com

# Cấp các quyền cần thiết
for ROLE in \
  roles/aiplatform.user \
  roles/discoveryengine.editor \
  roles/storage.objectAdmin \
  roles/datastore.user \
  roles/secretmanager.secretAccessor \
  roles/logging.logWriter \
  roles/cloudtrace.agent \
  roles/cloudtasks.enqueuer; do
  gcloud projects add-iam-policy-binding green-mercury-485016-n1 \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE"
done

# Tạo key cho dev local
gcloud iam service-accounts keys create key.json \
  --iam-account=$SA_EMAIL
echo "key.json" >> .gitignore
```

#### Bước 7: Tạo Cloud Tasks queue + Cloud Run IAM

```bash
# Tạo Cloud Tasks queue cho async generation
gcloud tasks queues create generation-queue \
  --location=asia-southeast1 \
  --max-dispatches-per-second=10 \
  --max-concurrent-dispatches=5 \
  --max-attempts=3 \
  --min-backoff=10s \
  --max-backoff=300s

# Xác minh
gcloud tasks queues describe generation-queue --location=asia-southeast1
```

```bash
# Cloud Run IAM cho upstream service (chạy sau khi deploy Cloud Run)
# Tạo upstream service account nếu chưa có:
gcloud iam service-accounts create upstream-svc \
  --display-name="Upstream Service"

UPSTREAM_SA=upstream-svc@green-mercury-485016-n1.iam.gserviceaccount.com

# Cấp quyền invoke (chạy sau T4.4 deploy)
# gcloud run services add-iam-policy-binding edu-game-ai-service \
#   --member="serviceAccount:$UPSTREAM_SA" \
#   --role="roles/run.invoker" \
#   --region=asia-southeast1
```

#### Xác minh toàn bộ setup

```bash
echo "=== APIs ==="
gcloud services list --enabled --filter="config.name:googleapis.com" | \
  grep -E "aiplatform|discoveryengine|run|firestore|storage|secretmanager|cloudbuild|logging|cloudtrace|cloudtasks"

echo "=== Bucket ==="
gsutil ls gs://edu-game-docs-green-mercury-485016-n1/

echo "=== Firestore ==="
gcloud firestore databases list

echo "=== Service Account ==="
gcloud iam service-accounts list --filter="email:edu-game-ai"

echo "=== Cloud Tasks Queue ==="
gcloud tasks queues list --location=asia-southeast1

echo "=== Secrets ==="
gcloud secrets list --filter="name:edu-game"
```

### Thiết lập Môi trường ✅ Xác nhận 2026-03-06

```bash
# Clone & install
git clone <repo-url> && cd AIServices
conda activate AIservice
pip install -e ".[dev]"

# Cấu hình env (ENV selector pattern)
cp .env.example .env          # Đặt ENV=develop hoặc ENV=product
cp .env.example .env.develop  # Chỉnh sửa giá trị development
cp .env.example .env.product  # Chỉnh sửa giá trị production
```

**ENV Selector Pattern** — `.env` chỉ chứa selector môi trường:

```env
# .env (chỉ selector - commit vào git dưới dạng .env.example)
ENV=develop
```

**Cấu hình Development** (`.env.develop`):

```env
# GCP Configuration
GCP_PROJECT_ID=green-mercury-485016-n1
GCP_LOCATION=asia-southeast1

# AI Search Configuration
DATA_STORE_ID=aiservice-datastore-m1_1772802306291
DATA_STORE_LOCATION=global

# Storage Configuration
GCS_BUCKET=documents-development-bucket
FIRESTORE_DATABASE=aiservice-store

# Cloud Tasks Configuration
CLOUD_TASKS_QUEUE=generation-queue
CLOUD_TASKS_LOCATION=asia-southeast1

# Application Configuration
SYSTEM_USER_ID=__system__
LOG_LEVEL=DEBUG
LOG_FORMAT=console
```

**Cấu hình Production** (`.env.product`) — cùng keys, giá trị production:

```env
# GCP Configuration
GCP_PROJECT_ID=<production-project-id>
GCP_LOCATION=asia-southeast1
# ... giá trị production
LOG_LEVEL=INFO
LOG_FORMAT=json
```

> ⚠️ **QUY TẮC:** Không được hardcode biến môi trường trong code. Tất cả config qua `get_settings()`

```bash
# Chạy dev server
uvicorn src.main:app --reload --port 8000
```

## Cấu trúc Code

**Code được tổ chức như thế nào?**

> **Trạng thái:** Core pipeline + tất cả services đã triển khai. API routes + deployment ⏸️ HOÃN (sẽ triển khai sau khi hoàn thành tất cả Pillars nội dung).

```
src/
├── api/                        # FastAPI — layer mỏng, delegate sang graph
│   ├── routes/
│   │   ├── documents.py        # User upload, list, status
│   │   ├── admin.py            # Admin: upload/list/delete system docs
│   │   ├── generate.py         # Trigger LangGraph, return results
│   │   └── game_types.py       # List available game types
│   ├── schemas/                # Pydantic API models
│   │   ├── requests.py         # GenerationRequest (với doc_scope)
│   │   ├── responses.py        # GameContentResponse, error models
│   │   └── game_content.py     # QuizQuestion, Flashcard, FillBlank, ContentItem
│   └── deps.py                 # Cloud Run IAM verification, user_id extraction từ body
├── graph/                      # LangGraph — TẤT CẢ BUSINESS LOGIC Ở ĐÂY
│   ├── builder.py              # StateGraph: nodes, edges, compile
│   ├── state.py                # AgentState TypedDict
│   └── nodes/
│       ├── supervisor.py       # Routing logic
│       ├── math_agent.py       # Phase 1: Toán/Lý/Hóa + Code Execution
│       ├── story_agent.py      # Phase 2: Văn/Sử + GraphRAG
│       ├── visual_agent.py     # Phase 3: Địa/Sinh + Multimodal
│       ├── structure_agent.py  # Phase 4: Ngữ pháp/Bảng + Table Parser
│       ├── reviewer.py         # Quality gate (Gemini Flash)
│       └── formatter.py        # Game template transform (Pydantic structured output)
├── templates/                  # Game type templates — extensible
│   ├── registry.py             # GAME_TEMPLATES dict: GameType → (Schema, prompt)
│   ├── quiz.py                 # QuizQuestion schema + formatter prompt
│   ├── flashcard.py            # Flashcard schema + formatter prompt
│   └── fill_blank.py           # FillBlankQuestion schema + formatter prompt
├── services/                   # GCP service wrappers (stateless)
│   ├── vertex_search.py        # VertexAISearchRetriever factory + doc_scope filter + user-first re-ranking
│   ├── llm.py                  # ChatVertexAI Pro/Flash factory
│   ├── document_store.py       # GCS upload (system/ + user/{user_id}/) + AI Search import
│   ├── firestore.py            # Firestore CRUD + job status tracking
│   └── task_queue.py           # Cloud Tasks dispatch cho async generation
├── config/
│   └── settings.py             # Pydantic BaseSettings
└── main.py                     # FastAPI app init
```

### Quy ước Đặt tên

- Files: `snake_case`
- Classes: `PascalCase`
- Functions/Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

## Ghi chú Triển khai

**Chi tiết kỹ thuật quan trọng cần nhớ:**

### Tính năng 1: LangGraph Graph (graph/builder.py)

```python
from langgraph.graph import StateGraph, END
from .state import AgentState

graph = StateGraph(AgentState)
graph.add_node("supervisor", supervisor_node)
graph.add_node("math_agent", math_agent_node)      # Phase 1
# graph.add_node("story_agent", story_agent_node)    # Phase 2
# graph.add_node("visual_agent", visual_agent_node)  # Phase 3
# graph.add_node("structure_agent", structure_agent_node)  # Phase 4
graph.add_node("reviewer", reviewer_node)
graph.add_node("formatter", formatter_node)

graph.set_entry_point("supervisor")
graph.add_conditional_edges(
    "supervisor",
    route_to_agent,
    {
        "math_agent": "math_agent",
        # "story_agent": "story_agent",      # Phase 2
        # "visual_agent": "visual_agent",    # Phase 3
        # "structure_agent": "structure_agent",  # Phase 4
    }
)
graph.add_edge("math_agent", "reviewer")
graph.add_conditional_edges("reviewer", review_router, {
    "pass": "formatter",
    "fail": "supervisor",  # feedback loop
})
graph.add_edge("formatter", END)

app = graph.compile(checkpointer=firestore_checkpointer)
```

### Tính năng 1.5: Async Generation via Cloud Tasks (services/task_queue.py)

```python
from google.cloud import tasks_v2
import json

def enqueue_generation(request_id: str, settings) -> str:
    """Dispatch generation job tới Cloud Tasks.

    Được gọi bởi POST /api/v1/generate sau khi tạo job record trong Firestore.
    Cloud Tasks sẽ trigger POST /internal/execute-generation/{request_id}
    trên cùng Cloud Run service.
    """
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        settings.GCP_PROJECT_ID,
        settings.CLOUD_TASKS_LOCATION,  # asia-southeast1
        settings.CLOUD_TASKS_QUEUE,     # generation-queue
    )

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{settings.CLOUD_RUN_URL}/internal/execute-generation/{request_id}",
            headers={"Content-Type": "application/json"},
            oidc_token=tasks_v2.OidcToken(
                service_account_email=settings.SERVICE_ACCOUNT_EMAIL,
            ),
        )
    )

    response = client.create_task(parent=parent, task=task)
    return response.name


# --- API route: POST /api/v1/generate ---
async def generate_endpoint(request: GenerationRequest):
    """Nhận generation request, enqueue async job, trả về ngay lập tức."""
    request_id = str(uuid4())

    # Lưu job vào Firestore
    await firestore.save_job({
        "request_id": request_id,
        "user_id": request.user_id,
        "status": "processing",
        "request": request.model_dump(),
        "created_at": datetime.utcnow(),
    })

    # Dispatch tới Cloud Tasks
    enqueue_generation(request_id, settings)

    return JSONResponse(
        status_code=202,
        content={
            "request_id": request_id,
            "status": "processing",
            "created_at": datetime.utcnow().isoformat(),
        },
    )


# --- Internal endpoint: POST /internal/execute-generation/{request_id} ---
async def execute_generation(request_id: str):
    """Được Cloud Tasks gọi. Chạy LangGraph pipeline và lưu kết quả."""
    job = await firestore.get_job(request_id)
    request = GenerationRequest(**job["request"])

    try:
        result = await langgraph_app.ainvoke(
            {"request": request, "doc_scope": request.doc_scope},
            config={"configurable": {"thread_id": request_id}},
        )
        await firestore.update_job(request_id, {
            "status": "completed",
            "content": result["final_output"].model_dump(),
            "completed_at": datetime.utcnow(),
        })
    except Exception as e:
        await firestore.update_job(request_id, {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.utcnow(),
        })
        raise  # Cloud Tasks sẽ retry
```

### Tính năng 2: Vertex AI Search + Doc Scope (services/vertex_search.py)

```python
from langchain_google_community import VertexAISearchRetriever

SYSTEM_USER_ID = "__system__"

def get_retriever(
    settings, user_id: str, doc_scope: str = "all"
) -> VertexAISearchRetriever:
    """Tạo retriever scoped theo doc_scope.

    doc_scope:
      - "user": chỉ documents cá nhân của user
      - "system": chỉ documents chung do admin quản lý
      - "all": cả user + system docs (mặc định) — user-first re-ranking
    """
    if doc_scope == "user":
        filter_str = f'user_id: ANY("{user_id}")'
    elif doc_scope == "system":
        filter_str = f'user_id: ANY("{SYSTEM_USER_ID}")'
    else:  # "all"
        filter_str = f'user_id: ANY("{user_id}", "{SYSTEM_USER_ID}")'

    return VertexAISearchRetriever(
        project_id=settings.GCP_PROJECT_ID,
        data_store_id=settings.DATA_STORE_ID,
        location_id=settings.GCP_LOCATION,  # "global"
        max_documents=5,
        max_extractive_answer_count=3,
        get_extractive_answers=True,
        filter=filter_str,
    )


def retrieve_with_user_first(
    retriever: VertexAISearchRetriever,
    query: str,
    doc_scope: str,
) -> list[Document]:
    """Retrieve docs và áp dụng user-first re-ranking cho doc_scope='all'.

    Post-retrieval re-ranking: user docs xếp trước, system docs bổ sung.
    """
    docs = retriever.invoke(query)

    if doc_scope != "all":
        return docs

    # User-first: sắp xếp user docs trước system docs
    user_docs = [d for d in docs if d.metadata.get("user_id") != SYSTEM_USER_ID]
    system_docs = [d for d in docs if d.metadata.get("user_id") == SYSTEM_USER_ID]
    return user_docs + system_docs
```

### Tính năng 3: Document Upload (User + System)

```python
from google.cloud import storage

SYSTEM_USER_ID = "__system__"

def upload_document(
    bucket_name: str,
    user_id: str,
    file: UploadFile,
    session_id: str,
    scope: str = "user",  # "user" | "system"
) -> str:
    """Upload lên GCS với path theo scope.

    System docs: gs://bucket/system/{date}/{session}/{filename}
    User docs:   gs://bucket/user/{user_id}/{date}/{session}/{filename}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if scope == "system":
        gcs_path = f"system/{today}/{session_id}/{file.filename}"
    else:
        gcs_path = f"user/{user_id}/{today}/{session_id}/{file.filename}"

    # Metadata user_id dùng __system__ cho system docs (AI Search filter)
    metadata_user_id = SYSTEM_USER_ID if scope == "system" else user_id

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.metadata = {
        "user_id": metadata_user_id,
        "upload_date": today,
        "session_id": session_id,
        "scope": scope,
    }
    blob.upload_from_file(file.file)
    return f"gs://{bucket_name}/{gcs_path}"
```

### Tính năng 4: Hệ thống Game Template (templates/registry.py)

```python
from src.api.schemas.game_content import (
    QuizQuestion, Flashcard, FillBlankQuestion
)

@dataclass
class GameTemplate:
    schema: type[BaseModel]
    formatter_prompt: str
    description: str

GAME_TEMPLATES: dict[str, GameTemplate] = {
    "quiz": GameTemplate(
        schema=QuizQuestion,
        formatter_prompt="Chuyển đổi các content items này thành câu hỏi trắc nghiệm với 4 lựa chọn...",
        description="Trắc nghiệm với 4 lựa chọn",
    ),
    "flashcard": GameTemplate(
        schema=Flashcard,
        formatter_prompt="Chuyển đổi các content items này thành flashcards...",
        description="Flashcard trước/sau để ghi nhớ",
    ),
    "fill_blank": GameTemplate(
        schema=FillBlankQuestion,
        formatter_prompt="Chuyển đổi các content items này thành câu điền vào chỗ trống...",
        description="Câu với chỗ trống để điền",
    ),
}
```

### Tính năng 5: Code Execution trong Math Agent

```python
from langchain_google_vertexai import ChatVertexAI

model = ChatVertexAI(
    model="gemini-2.0-flash",
    tools=[{"code_execution": {"mode": "advanced"}}],
)
# Agent prompt yêu cầu model giải toán bằng Python, trả về đáp án số
```

### Tính năng 6: Formatter với Dynamic Schema

```python
def formatter_node(state: AgentState) -> dict:
    """Transform content items thành game-specific output theo loại được yêu cầu."""
    results = {}
    for game_type in state["request"].game_types:
        template = GAME_TEMPLATES[game_type]
        llm = ChatVertexAI(model="gemini-2.0-flash")
        structured_llm = llm.with_structured_output(
            list[template.schema]  # Dynamic schema theo game type
        )
        items = structured_llm.invoke(
            template.formatter_prompt + "\n" + json.dumps(state["reviewed_items"])
        )
        results[game_type] = [item.model_dump() for item in items]
    return {"final_output": build_response(state, results)}
```

### Tính năng 7: Cloud Run IAM Auth Middleware (api/deps.py)

```python
from fastapi import Request, HTTPException

async def verify_upstream_caller(request: Request):
    """Xác minh request đến từ upstream service được ủy quyền.

    Khi Cloud Run được deploy với --no-allow-unauthenticated,
    GCP tự động xác minh IAM identity của caller.
    Chỉ service accounts có roles/run.invoker mới gọi được.

    Với local dev: bỏ qua kiểm tra IAM, tin tưởng tất cả callers.
    """
    if settings.ENVIRONMENT == "local":
        return  # Bỏ qua cho phát triển local

    # Cloud Run xử lý xác minh IAM ở tầng infrastructure.
    # Nếu request tới được điểm này, caller đã được ủy quyền.
    # Tùy chọn xác minh X-Cloud-Tasks-TaskName header cho internal endpoints.
    pass


def extract_user_id(request: GenerationRequest) -> str:
    """Trích xuất user_id từ request body.

    user_id là giá trị được tin tưởng từ upstream service.
    Upstream đã xác thực user rồi.
    """
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id là bắt buộc")
    return request.user_id
```

### Patterns & Best Practices

- **LangGraph nodes là pure functions:** `fn(state: AgentState) -> dict` — trả về partial state updates
- **Async-first:** Tất cả generation requests đi qua Cloud Tasks, không sync. POST /generate trả về 202 ngay lập tức.
- **Doc scope ở mọi nơi:** Mọi query dùng `doc_scope` để xác định filter. System docs luôn accessible. User docs scoped theo user_id.
- **Service-to-service trust:** Cloud Run IAM đảm bảo chỉ upstream gọi được. `user_id` từ body được tin tưởng.
- **Dependency Injection:** FastAPI `Depends` cho Firestore client, settings
- **Config-driven:** Model selection, max retries, Data Store ID, `SYSTEM_USER_ID`, Cloud Tasks queue đều từ settings
- **Idempotency:** Mỗi generation có request_id duy nhất
- **Game template extensibility:** Thêm game mới = thêm vào `templates/` + đăng ký trong `registry.py`

## Điểm Tích hợp

**Các phần kết nối như thế nào?**

| Tích hợp         | Package                       | Sử dụng                                             |
| ---------------- | ----------------------------- | --------------------------------------------------- |
| Vertex AI (LLM)  | `langchain-google-vertexai`   | `ChatVertexAI` cho Gemini Pro/Flash                 |
| Vertex AI Search | `langchain-google-community`  | `VertexAISearchRetriever` + doc_scope filter        |
| Cloud Storage    | `google-cloud-storage`        | Doc upload (thư mục `system/` + `user/{user_id}/`)  |
| Firestore        | `google-cloud-firestore`      | JSON output, metadata, checkpoints, job status      |
| Cloud Tasks      | `google-cloud-tasks`          | Async generation dispatch, retry, dead-letter queue |
| Secret Manager   | `google-cloud-secret-manager` | Cấu hình service lúc runtime                        |

## Xử lý Lỗi

**Chúng ta xử lý failures như thế nào?**

| Lỗi                                | Chiến lược                                    |
| ---------------------------------- | --------------------------------------------- |
| Lỗi Gemini API                     | Retry 3x, exponential backoff (1s, 2s, 4s)    |
| Vertex AI Search không có kết quả  | Retry với query viết lại, sau đó trả 400      |
| Vertex AI Search doc đang indexing | Trả 409 "Document đang được index"            |
| Code Execution timeout             | Retry với prompt đơn giản hơn, tối đa 3x      |
| Schema validation fail             | Log output lỗi, retry generation              |
| Reviewer reject                    | LangGraph feedback loop, tối đa 3 iterations  |
| File format không hợp lệ           | Trả 400 với định dạng hỗ trợ: PDF, DOCX, PPTX |
| File quá lớn (>50MB)               | Trả 413                                       |
| Vi phạm user doc scope             | Trả 403                                       |

### Logging

- `structlog` định dạng JSON → Cloud Logging
- Fields: `request_id`, `user_id`, `node_name`, `model`, `token_count`, `latency_ms`, `ai_search_queries`

## Cân nhắc Hiệu suất

**Làm sao giữ cho nhanh?**

- **Vertex AI Search:** Pre-indexed → query latency ~1-2s
- **Gemini Flash cho Reviewer/Formatter:** ms-level latency
- **Batch generation:** Single LLM call cho nhiều content items
- **Async I/O:** FastAPI + async Firestore + async GCS
- **Cloud Run concurrency:** max_concurrency=10 per instance

## Ghi chú Bảo mật

**Những biện pháp bảo mật nào đã có?**

- **Service-to-service auth:** Cloud Run IAM — deploy với `--no-allow-unauthenticated`. Chỉ upstream service account (có `roles/run.invoker`) mới gọi được.
- **Trusted `user_id`:** Upstream đã xác minh user → `user_id` trong request body là đáng tin cậy. AI Service dùng trực tiếp để scope data.
- **Admin operations:** Upstream gọi với admin context (`scope: "system"`). AI Service tin tưởng upstream đã ủy quyền.
- **Internal endpoints:** Routes `/internal/*` chỉ Cloud Tasks gọi (xác minh header `X-CloudTasks-TaskName`).
- **User scoping:** `user_id` từ request body → tất cả queries lọc theo user_id (trừ doc_scope=system)
- **Input:** Pydantic validation, chỉ PDF/DOCX/PPTX (magic bytes check + extension), giới hạn 50MB
- **GCS:** Uniform bucket-level access, files namespaced: `system/` cho admin docs, `user/{user_id}/` cho user docs
- **Privacy:** User docs là private (scoped). System docs là shared. Chính sách consent theo Requirements. Documents không dùng để training/fine-tuning.
- **Vertex AI Search:** Metadata filter đảm bảo user isolation + system docs access
- **GCP IAM:** Service account với least-privilege roles:
  - `roles/aiplatform.user` (Vertex AI)
  - `roles/discoveryengine.editor` (AI Search query + import)
  - `roles/storage.objectAdmin` (GCS upload/read)
  - `roles/datastore.user` (Firestore)
  - `roles/secretmanager.secretAccessor` (Cấu hình service)
  - `roles/cloudtasks.enqueuer` (Cloud Tasks dispatch)
  - `roles/logging.logWriter` (Cloud Logging)
  - `roles/cloudtrace.agent` (Cloud Trace)
- **Secrets:** Secret Manager cho cấu hình service. `key.json` trong `.gitignore`.

```

```
