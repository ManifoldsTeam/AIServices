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
- `uv` cho dependency management

### GCP Project Setup (APIs Enabled → Setup Resources)

Project `green-mercury-485016-n1` đã **enable tất cả APIs cần thiết**. Chạy setup dưới đây để tạo resources trước khi bắt đầu code.

#### Step 1: Authenticate & set project

```bash
gcloud auth login
gcloud config set project green-mercury-485016-n1
gcloud auth application-default login

# Verify
gcloud config list
```

#### Step 2: Enable ALL required APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com

# Verify (should show at least 9 APIs)
gcloud services list --enabled --filter="config.name:googleapis.com" | wc -l
```

#### Step 3: Create Cloud Storage bucket

```bash
# Bucket cho document upload (system + user)
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
  roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding green-mercury-485016-n1 \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE"
done

# Generate key for local dev
gcloud iam service-accounts keys create key.json \
  --iam-account=$SA_EMAIL
echo "key.json" >> .gitignore
```

#### Step 7: Create API Key + Admin Key secrets

```bash
# User API key
echo -n "$(openssl rand -hex 32)" | \
  gcloud secrets create edu-game-api-key \
  --data-file=- --replication-policy=automatic

# Admin API key (for system docs management)
echo -n "$(openssl rand -hex 32)" | \
  gcloud secrets create edu-game-admin-key \
  --data-file=- --replication-policy=automatic

# Verify
gcloud secrets versions access latest --secret=edu-game-api-key
gcloud secrets versions access latest --secret=edu-game-admin-key
```

#### Verify full setup

```bash
echo "=== APIs ==="
gcloud services list --enabled --filter="config.name:googleapis.com" | \
  grep -E "aiplatform|discoveryengine|run|firestore|storage|secretmanager|cloudbuild|logging|cloudtrace"

echo "=== Bucket ==="
gsutil ls gs://edu-game-docs-green-mercury-485016-n1/

echo "=== Firestore ==="
gcloud firestore databases list

echo "=== Service Account ==="
gcloud iam service-accounts list --filter="email:edu-game-ai"

echo "=== Secrets ==="
gcloud secrets list --filter="name:edu-game"
```

### Environment Setup

```bash
# Clone & install
git clone <repo-url> && cd AIServices
uv sync

# Configure env
cp .env.example .env
```

`.env.example`:

```env
GCP_PROJECT_ID=green-mercury-485016-n1
GCP_LOCATION=global
DATA_STORE_ID=edu-game-docs
GCS_BUCKET=edu-game-docs-green-mercury-485016-n1
GOOGLE_APPLICATION_CREDENTIALS=key.json
API_KEY_SECRET_ID=edu-game-api-key
ADMIN_KEY_SECRET_ID=edu-game-admin-key
SYSTEM_USER_ID=__system__
```

```bash
# Run dev server
uvicorn src.main:app --reload --port 8000
```

## Code Structure

**How is the code organized?**

```
src/
├── api/                        # FastAPI — thin layer, delegates to graph
│   ├── routes/
│   │   ├── documents.py        # User upload, list, status
│   │   ├── admin.py            # Admin: upload/list/delete system docs
│   │   ├── generate.py         # Trigger LangGraph, return results
│   │   └── game_types.py       # List available game types
│   ├── schemas/                # Pydantic API models
│   │   ├── requests.py         # GenerationRequest (with doc_scope)
│   │   ├── responses.py        # GameContentResponse, error models
│   │   └── game_content.py     # QuizQuestion, Flashcard, FillBlank, ContentItem
│   └── deps.py                 # API key auth, admin key auth, user_id extraction
├── graph/                      # LangGraph — ALL BUSINESS LOGIC LIVES HERE
│   ├── builder.py              # StateGraph: nodes, edges, compile
│   ├── state.py                # AgentState TypedDict
│   └── nodes/
│       ├── supervisor.py       # Routing logic
│       ├── content_agent.py    # Query AI Search (user-scoped) + generate + Code Exec
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
│   └── firestore.py            # Firestore CRUD
├── config/
│   └── settings.py             # Pydantic BaseSettings
└── main.py                     # FastAPI app init
```

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
graph.add_node("content_agent", content_agent_node)
graph.add_node("reviewer", reviewer_node)
graph.add_node("formatter", formatter_node)

graph.set_entry_point("supervisor")
graph.add_edge("supervisor", "content_agent")      # MVP: direct route
graph.add_edge("content_agent", "reviewer")
graph.add_conditional_edges("reviewer", review_router, {
    "pass": "formatter",
    "fail": "supervisor",  # feedback loop
})
graph.add_edge("formatter", END)

app = graph.compile(checkpointer=firestore_checkpointer)
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

    Post-retrieval re-ranking: user docs xếp trước, system docs bổ sung.
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

    # Metadata user_id vẫn dùng __system__ cho system docs (AI Search filter)
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

### Feature 5: Code Execution in Content Agent

```python
from langchain_google_vertexai import ChatVertexAI

model = ChatVertexAI(
    model="gemini-2.0-flash",
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
        llm = ChatVertexAI(model="gemini-2.0-flash")
        structured_llm = llm.with_structured_output(
            list[template.schema]  # Dynamic schema per game type
        )
        items = structured_llm.invoke(
            template.formatter_prompt + "\n" + json.dumps(state["reviewed_items"])
        )
        results[game_type] = [item.model_dump() for item in items]
    return {"final_output": build_response(state, results)}
```

### Patterns & Best Practices

- **LangGraph nodes are pure functions:** `fn(state: AgentState) -> dict` — return partial state updates
- **Doc scope everywhere:** Every query uses `doc_scope` to determine filter. System docs always accessible. User docs scoped per user_id.
- **Dependency Injection:** FastAPI `Depends` cho Firestore client, settings
- **Config-driven:** Model selection, max retries, Data Store ID, `SYSTEM_USER_ID` all from settings
- **Idempotency:** Each generation has unique request_id
- **Game template extensibility:** Adding new game = add to `templates/` + register in `registry.py`
- **Admin isolation:** Admin endpoints require separate `X-Admin-Key`, use `__system__` as user_id

## Integration Points

**How do pieces connect?**

| Integration      | Package                       | Usage                                              |
| ---------------- | ----------------------------- | -------------------------------------------------- |
| Vertex AI (LLM)  | `langchain-google-vertexai`   | `ChatVertexAI` for Gemini Pro/Flash                |
| Vertex AI Search | `langchain-google-community`  | `VertexAISearchRetriever` + doc_scope filter       |
| Cloud Storage    | `google-cloud-storage`        | Doc upload (`system/` + `user/{user_id}/` folders) |
| Firestore        | `google-cloud-firestore`      | JSON output, metadata, checkpoints, doc records    |
| Secret Manager   | `google-cloud-secret-manager` | API keys at runtime                                |

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

- **API Key:** `X-API-Key` header, validate from Secret Manager
- **Admin Key:** `X-Admin-Key` header for admin endpoints, separate secret
- **User scoping:** `X-User-Id` header → all queries filtered by user_id (unless doc_scope=system)
- **Input:** Pydantic validation, PDF/DOCX/PPTX only (magic bytes check + extension), 50MB limit
- **GCS:** Uniform bucket-level access, files namespaced: `system/` for admin docs, `user/{user_id}/` for user docs
- **Privacy:** User docs are private (scoped). System docs are shared. Consent policy per Requirements. Không dùng docs cho training/fine-tuning.
- **Vertex AI Search:** Metadata filter enforces user isolation + system docs access
- **GCP IAM:** Service account with least-privilege roles:
  - `roles/aiplatform.user` (Vertex AI)
  - `roles/discoveryengine.editor` (AI Search query + import)
  - `roles/storage.objectAdmin` (GCS upload/read)
  - `roles/datastore.user` (Firestore)
  - `roles/secretmanager.secretAccessor` (API keys)
  - `roles/logging.logWriter` (Cloud Logging)
  - `roles/cloudtrace.agent` (Cloud Trace)
- **Secrets:** Secret Manager, never in env vars or code. `key.json` in `.gitignore`.
