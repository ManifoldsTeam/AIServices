````markdown
---
phase: implementation
title: Implementation Guide
description: Technical implementation notes, patterns, and code guidelines
---

# Implementation Guide

## Development Setup

**How do we get started?**

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- `gcloud` CLI installed & authenticated
- `uv` for dependency management

### GCP Project Setup (APIs Enabled → Setup Resources)

Project `green-mercury-485016-n1` has **enabled all required APIs**. Run the setup below to create resources before starting code.

#### Step 1: Authenticate & set project

```bash
gcloud auth login
gcloud config set project green-mercury-485016-n1
gcloud auth application-default login

# Verify
gcloud config list
```
````

#### Step 2: Enable ALL required APIs

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

# Verify (should show at least 10 APIs)
gcloud services list --enabled --filter="config.name:googleapis.com" | wc -l
```

#### Step 3: Create Cloud Storage bucket

```bash
# Bucket for document upload (system + user)
gsutil mb -b on -l asia-southeast1 \
  gs://edu-game-docs-green-mercury-485016-n1

# Test: create folder structure
# System docs
echo "test" | gsutil cp - \
  gs://edu-game-docs-green-mercury-485016-n1/system/2026-03-03/session-1/test.txt
# User docs
echo "test" | gsutil cp - \
  gs://edu-game-docs-green-mercury-485016-n1/user/test-user/2026-03-03/session-1/test.txt

gsutil ls gs://edu-game-docs-green-mercury-485016-n1/system/
gsutil ls gs://edu-game-docs-green-mercury-485016-n1/user/test-user/

# Cleanup test files
gsutil rm gs://edu-game-docs-green-mercury-485016-n1/system/2026-03-03/session-1/test.txt
gsutil rm gs://edu-game-docs-green-mercury-485016-n1/user/test-user/2026-03-03/session-1/test.txt
```

#### Step 4: Create Firestore database

```bash
gcloud firestore databases create --location=asia-southeast1

# Verify
gcloud firestore databases list
```

#### Step 5: Create Vertex AI Search Data Store

Via GCP Console (recommended for first setup):

1. Go to **Agent Builder** → **Data Stores** → **Create**
2. Source: **Cloud Storage**
3. Select bucket: `edu-game-docs-green-mercury-485016-n1`
4. Data type: **Unstructured documents**
5. Name: `edu-game-docs`
6. Create → note the `DATA_STORE_ID`

Or via REST API:

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

Then create a Search App:

1. Agent Builder → **Apps** → **Create**
2. Type: **Search** → Generic
3. Link to `edu-game-docs` Data Store

#### Step 6: Create Service Account

```bash
gcloud iam service-accounts create edu-game-ai \
  --display-name="Edu Game AI Service"

SA_EMAIL=edu-game-ai@green-mercury-485016-n1.iam.gserviceaccount.com

# Grant required roles
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

# Generate key for local dev
gcloud iam service-accounts keys create key.json \
  --iam-account=$SA_EMAIL
echo "key.json" >> .gitignore
```

#### Step 7: Create Cloud Tasks queue + Cloud Run IAM

```bash
# Create Cloud Tasks queue for async generation
gcloud tasks queues create generation-queue \
  --location=asia-southeast1 \
  --max-dispatches-per-second=10 \
  --max-concurrent-dispatches=5 \
  --max-attempts=3 \
  --min-backoff=10s \
  --max-backoff=300s

# Verify
gcloud tasks queues describe generation-queue --location=asia-southeast1
```

```bash
# Cloud Run IAM for upstream service (run after deploying Cloud Run)
# Create upstream service account if not existing:
gcloud iam service-accounts create upstream-svc \
  --display-name="Upstream Service"

UPSTREAM_SA=upstream-svc@green-mercury-485016-n1.iam.gserviceaccount.com

# Grant invoke permission (run after T4.4 deploy)
# gcloud run services add-iam-policy-binding edu-game-ai-service \
#   --member="serviceAccount:$UPSTREAM_SA" \
#   --role="roles/run.invoker" \
#   --region=asia-southeast1
```

#### Verify full setup

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

### Environment Setup ✅ Verified 2026-03-06

```bash
# Clone & install
git clone <repo-url> && cd AIServices
conda activate AIservice
pip install -e ".[dev]"

# Configure env (ENV selector pattern)
cp .env.example .env          # Set ENV=develop or ENV=product
cp .env.example .env.develop  # Edit with development values
cp .env.example .env.product  # Edit with production values
```

**ENV Selector Pattern** — `.env` contains only the environment selector:

```env
# .env (selector only - committed to git as .env.example)
ENV=develop
```

**Development Configuration** (`.env.develop`):

```env
# GCP Configuration
GCP_PROJECT_ID=green-mercury-485016-n1
GCP_LOCATION=asia-southeast1

# AI Search Configuration
DATA_STORE_ID=aiservice-datastore-m1_1772802306291
SEARCH_ENGINE_ID=gp-mathagent_1773042630372
DATA_STORE_LOCATION=global

# Vertex AI Models (env-configurable, no code changes needed)
# GA: gemini-2.5-flash | gemini-2.5-flash-lite | gemini-2.5-pro
# Preview: gemini-3-flash-preview | gemini-3.1-pro-preview | gemini-3.1-flash-lite-preview
GENERATION_MODEL=gemini-2.5-flash
REVIEW_MODEL=gemini-3.1-flash-lite-preview
REVIEW_MODEL_LOCATION=global

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

# LangSmith Tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=edu-game-ai-dev
# LANGCHAIN_API_KEY=lsv2_pt_XXXXXXXX
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

**Production Configuration** (`.env.product`) — same keys, production values:

```env
# GCP Configuration
GCP_PROJECT_ID=<production-project-id>
GCP_LOCATION=asia-southeast1
# ... production values
LOG_LEVEL=INFO
LOG_FORMAT=json
```

> ⚠️ **RULE:** No hardcoding environment variables in code. All config via `get_settings()`

```bash
# Run dev server
uvicorn src.main:app --reload --port 8000
```

## Code Structure (Verified 2026-03-11)

**How is the code organized?**

> **Status:** Core pipeline + all services implemented. API routes + deployment ⏸️ DEFERRED (will be done after all content Pillars are complete).

```
src/
├── api/                        # FastAPI — thin layer, delegates to graph
│   ├── schemas/                # ✅ ALL Pydantic API models IMPLEMENTED
│   │   ├── requests.py         # ✅ DocScope, GenerationRequest, DocumentUploadRequest, AdminDocumentUploadRequest
│   │   ├── responses.py        # ✅ JobStatus, GenerationMetadata, GameContentResponse, JobResponse, DocumentResponse, ErrorResponse
│   │   └── game_content.py     # ✅ GameType, DifficultyLevel, QuizQuestion, QuizOption, Flashcard, FillBlankQuestion, BlankSlot, ContentItem
│   ├── routes/                 # ⏳ NOT YET IMPLEMENTED
│   │   ├── documents.py        # User upload, list, status
│   │   ├── admin.py            # Admin: upload/list/delete system docs
│   │   ├── generate.py         # Trigger LangGraph, return results
│   │   └── game_types.py       # List available game types
│   └── deps.py                 # ⏳ Cloud Run IAM verification, user_id extraction
├── graph/                      # ✅ LangGraph — ALL BUSINESS LOGIC IMPLEMENTED
│   ├── builder.py              # ✅ StateGraph: START → supervisor → math_agent → reviewer → (formatter→END | supervisor loop)
│   ├── state.py                # ✅ AgentState TypedDict (request, search_context, content/reviewed/rejected items, iteration_count, final_output, errors)
│   └── nodes/
│       ├── supervisor.py       # ✅ Content classification + routing
│       ├── math_agent.py       # ✅ Phase 1: Math/Physics/Chem + Vertex AI Search + structured output
│       ├── reviewer.py         # ✅ Quality gate (pass ≥0.7), feedback with rejection reasons
│       └── formatter.py        # ✅ Game template transform: quiz, flashcard, fill_blank sub-formatters
├── services/                   # ✅ ALL GCP service wrappers IMPLEMENTED
│   ├── vertex_search.py        # ✅ VertexAISearchRetriever factory + doc_scope filter + user-first re-ranking + engine-level serving config override
│   ├── llm.py                  # ✅ get_generation_llm(), get_review_llm(), get_structured_llm() — per-model location support
│   ├── document_store.py       # ✅ GCS upload (system/ + user/{user_id}/) + AI Search import + file validation
│   ├── firestore.py            # ✅ Async Firestore CRUD: create/get/update/complete/fail job + document records
│   └── task_queue.py           # ✅ Cloud Tasks dispatch with OIDC auth for async generation
├── config/
│   ├── settings.py             # ✅ Pydantic BaseSettings (GENERATION_MODEL, REVIEW_MODEL, per-model locations)
│   ├── constants.py            # ✅ LLM temps/tokens, file limits, MIME types
│   └── logging.py              # ✅ structlog console/JSON setup
└── main.py                     # ⏳ FastAPI app init — NOT YET CREATED
```

**Notes:**

- `templates/` directory NOT created — formatters inline in `formatter.py`
- Story/Visual/Structure agents NOT created (Phase 2+)
- No `routes/` or `deps.py` yet — needs FastAPI API layer

### Naming Conventions

- Files: `snake_case`
- Classes: `PascalCase`
- Functions/Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

## Implementation Notes

**Key technical details to remember:**

### Feature 1: LangGraph Graph (graph/builder.py)

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

### Feature 1.5: Async Generation via Cloud Tasks (services/task_queue.py)

```python
from google.cloud import tasks_v2
import json

def enqueue_generation(request_id: str, settings) -> str:
    """Dispatch generation job to Cloud Tasks.

    Called by POST /api/v1/generate after creating job record in Firestore.
    Cloud Tasks will trigger POST /internal/execute-generation/{request_id}
    on the same Cloud Run service.
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
    """Accept generation request, enqueue async job, return immediately."""
    request_id = str(uuid4())

    # Save job to Firestore
    await firestore.save_job({
        "request_id": request_id,
        "user_id": request.user_id,
        "status": "processing",
        "request": request.model_dump(),
        "created_at": datetime.utcnow(),
    })

    # Dispatch to Cloud Tasks
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
    """Called by Cloud Tasks. Runs LangGraph pipeline and saves result."""
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
        raise  # Cloud Tasks will retry
```

### Feature 2: Vertex AI Search + Doc Scope (services/vertex_search.py)

```python
from langchain_google_community import VertexAISearchRetriever

SYSTEM_USER_ID = "__system__"

def get_retriever(
    settings, user_id: str, doc_scope: str = "all"
) -> VertexAISearchRetriever:
    """Create retriever scoped by doc_scope.

    doc_scope:
      - "user": only user's personal documents
      - "system": only admin-managed shared documents
      - "all": both user + system docs (default) — user-first re-ranking
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
    """Retrieve docs and apply user-first re-ranking for doc_scope='all'.

    Post-retrieval re-ranking: user docs ranked first, system docs supplement.
    """
    docs = retriever.invoke(query)

    if doc_scope != "all":
        return docs

    # User-first: sort user docs before system docs
    user_docs = [d for d in docs if d.metadata.get("user_id") != SYSTEM_USER_ID]
    system_docs = [d for d in docs if d.metadata.get("user_id") == SYSTEM_USER_ID]
    return user_docs + system_docs
```

### Feature 3: Document Upload (User + System)

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
    """Upload to GCS with scope-aware path.

    System docs: gs://bucket/system/{date}/{session}/{filename}
    User docs:   gs://bucket/user/{user_id}/{date}/{session}/{filename}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if scope == "system":
        gcs_path = f"system/{today}/{session_id}/{file.filename}"
    else:
        gcs_path = f"user/{user_id}/{today}/{session_id}/{file.filename}"

    # Metadata user_id uses __system__ for system docs (AI Search filter)
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

### Feature 4: Game Template System (templates/registry.py)

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
        formatter_prompt="Transform these content items into quiz questions with 4 options...",
        description="Multiple choice quiz with 4 options",
    ),
    "flashcard": GameTemplate(
        schema=Flashcard,
        formatter_prompt="Transform these content items into flashcards...",
        description="Front/back flashcards for memorization",
    ),
    "fill_blank": GameTemplate(
        schema=FillBlankQuestion,
        formatter_prompt="Transform these content items into fill-in-the-blank questions...",
        description="Sentences with blanks to fill in",
    ),
}
```

### Feature 5: Code Execution in Math Agent

```python
from langchain_google_vertexai import ChatVertexAI
from src.config import get_settings

settings = get_settings()
model = ChatVertexAI(
    model=settings.generation_model,  # env-configurable: gemini-2.5-flash
    tools=[{"code_execution": {"mode": "advanced"}}],
)
# Agent prompt asks model to solve math using Python, return numerical answer
```

### Feature 6: Formatter with Dynamic Schema

```python
def formatter_node(state: AgentState) -> dict:
    """Transform content items into game-specific output per requested type."""
    results = {}
    for game_type in state["request"].game_types:
        template = GAME_TEMPLATES[game_type]
        llm = ChatVertexAI(model=settings.generation_model)  # env-configurable
        structured_llm = llm.with_structured_output(
            list[template.schema]  # Dynamic schema per game type
        )
        items = structured_llm.invoke(
            template.formatter_prompt + "\n" + json.dumps(state["reviewed_items"])
        )
        results[game_type] = [item.model_dump() for item in items]
    return {"final_output": build_response(state, results)}
```

### Feature 7: Cloud Run IAM Auth Middleware (api/deps.py)

```python
from fastapi import Request, HTTPException

async def verify_upstream_caller(request: Request):
    """Verify request comes from authorized upstream service.

    When Cloud Run is deployed with --no-allow-unauthenticated,
    GCP automatically verifies the caller's IAM identity.
    Only service accounts with roles/run.invoker can call.

    For local dev: skip IAM check, trust all callers.
    """
    if settings.ENVIRONMENT == "local":
        return  # Skip for local development

    # Cloud Run handles IAM verification at infrastructure level.
    # If request reaches this point, caller is already authorized.
    # Optionally verify X-Cloud-Tasks-TaskName header for internal endpoints.
    pass


def extract_user_id(request: GenerationRequest) -> str:
    """Extract user_id from request body.

    user_id is a trusted value from upstream service.
    Upstream has already authenticated the user.
    """
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    return request.user_id
```

### Patterns & Best Practices

- **LangGraph nodes are pure functions:** `fn(state: AgentState) -> dict` — return partial state updates
- **Async-first:** All generation requests go through Cloud Tasks, not sync. POST /generate returns 202 immediately.
- **Doc scope everywhere:** Every query uses `doc_scope` to determine filter. System docs always accessible. User docs scoped per user_id.
- **Service-to-service trust:** Cloud Run IAM ensures only upstream can call. `user_id` from body is trusted.
- **Dependency Injection:** FastAPI `Depends` for Firestore client, settings
- **Config-driven:** Model selection via `Settings.generation_model`/`Settings.review_model` (env vars), tuning params in `src/config/constants.py`, Data Store ID, `SYSTEM_USER_ID`, Cloud Tasks queue all from settings
- **Idempotency:** Each generation has unique request_id
- **Game template extensibility:** Adding new game = add to `templates/` + register in `registry.py`

## Integration Points

**How do pieces connect?**

| Integration      | Package                       | Usage                                               |
| ---------------- | ----------------------------- | --------------------------------------------------- |
| Vertex AI (LLM)  | `langchain-google-vertexai`   | `ChatVertexAI` for Gemini Pro/Flash                 |
| Vertex AI Search | `langchain-google-community`  | `VertexAISearchRetriever` + doc_scope filter        |
| Cloud Storage    | `google-cloud-storage`        | Doc upload (`system/` + `user/{user_id}/` folders)  |
| Firestore        | `google-cloud-firestore`      | JSON output, metadata, checkpoints, job status      |
| Cloud Tasks      | `google-cloud-tasks`          | Async generation dispatch, retry, dead-letter queue |
| Secret Manager   | `google-cloud-secret-manager` | Service configuration at runtime                    |

## Known Technical Issues & Workarounds (Verified 2026-03-11)

| Issue                                                                  | Workaround                                                                                 | Status                |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | --------------------- |
| `VertexAISearchRetriever._serving_config` builds datastore-level path  | Override with engine-level path via `_apply_engine_serving_config()` in `vertex_search.py` | ✅ Fixed              |
| Extractive answers require Enterprise tier                             | Upgraded engine to `SEARCH_TIER_ENTERPRISE` via SDK `update_engine()`                      | ✅ Fixed              |
| `gemini-2.5-flash-lite` model not found                                | Changed to `gemini-3.1-flash-lite-preview` (Preview, global only)                          | ✅ Fixed              |
| Per-model location mismatch (review model needs global)                | Added `generation_model_location`/`review_model_location` to Settings                      | ✅ Fixed              |
| `usage_metadata` can be `dict` not object                              | Use `isinstance` check before attribute access                                             | ✅ Fixed in notebooks |
| `gemini-3.1-flash-lite-preview` returns parts with `thought_signature` | `response.content` is list of parts — handle accordingly                                   | ⚠️ Known              |
| `ChatVertexAI` deprecated in LangChain 3.2.0                           | Migrate to `langchain-google-genai` / `ChatGoogleGenerativeAI`                             | ⏳ Tech debt          |

## Error Handling

**How do we handle failures?**

| Error                               | Strategy                                           |
| ----------------------------------- | -------------------------------------------------- |
| Gemini API error                    | Retry 3x, exponential backoff (1s, 2s, 4s)         |
| Vertex AI Search no results         | Retry with rephrased query, then return 400        |
| Vertex AI Search doc still indexing | Return 409 "Document still indexing"               |
| Code Execution timeout              | Retry with simplified prompt, max 3x               |
| Schema validation fail              | Log malformed output, retry generation             |
| Reviewer rejection                  | LangGraph feedback loop, max 3 iterations          |
| Invalid file format                 | Return 400 with supported formats: PDF, DOCX, PPTX |
| File too large (>50MB)              | Return 413                                         |
| User doc scope violation            | Return 403                                         |

### Logging

- `structlog` JSON format → Cloud Logging
- Fields: `request_id`, `user_id`, `node_name`, `model`, `token_count`, `latency_ms`, `ai_search_queries`

## Performance Considerations

**How do we keep it fast?**

- **Vertex AI Search:** Pre-indexed → query latency ~1-2s
- **Gemini Flash for Reviewer/Formatter:** ms-level latency
- **Batch generation:** Single LLM call for multiple content items
- **Async I/O:** FastAPI + async Firestore + async GCS
- **Cloud Run concurrency:** max_concurrency=10 per instance

## Security Notes

**What security measures are in place?**

- **Service-to-service auth:** Cloud Run IAM — deploy with `--no-allow-unauthenticated`. Only upstream service account (with `roles/run.invoker`) can call.
- **Trusted `user_id`:** Upstream has verified user → `user_id` in request body is trustworthy. AI Service uses directly to scope data.
- **Admin operations:** Upstream calls with admin context (`scope: "system"`). AI Service trusts upstream has already authorized.
- **Internal endpoints:** `/internal/*` routes only called by Cloud Tasks (verify `X-CloudTasks-TaskName` header).
- **User scoping:** `user_id` from request body → all queries filtered by user_id (unless doc_scope=system)
- **Input:** Pydantic validation, PDF/DOCX/PPTX only (magic bytes check + extension), 50MB limit
- **GCS:** Uniform bucket-level access, files namespaced: `system/` for admin docs, `user/{user_id}/` for user docs
- **Privacy:** User docs are private (scoped). System docs are shared. Consent policy per Requirements. Documents not used for training/fine-tuning.
- **Vertex AI Search:** Metadata filter enforces user isolation + system docs access
- **GCP IAM:** Service account with least-privilege roles:
  - `roles/aiplatform.user` (Vertex AI)
  - `roles/discoveryengine.editor` (AI Search query + import)
  - `roles/storage.objectAdmin` (GCS upload/read)
  - `roles/datastore.user` (Firestore)
  - `roles/secretmanager.secretAccessor` (Service config)
  - `roles/cloudtasks.enqueuer` (Cloud Tasks dispatch)
  - `roles/logging.logWriter` (Cloud Logging)
  - `roles/cloudtrace.agent` (Cloud Trace)
- **Secrets:** Secret Manager for service configuration. `key.json` in `.gitignore`.

```

```
