# Edu Game AI Service

Async AI-powered content generation service for educational games. Generates quiz questions, flashcards, and fill-in-the-blank content from Vietnamese high school textbooks using Gemini + Vertex AI Search.

## Architecture

- **Framework**: FastAPI + LangGraph
- **LLM**: Gemini 2.5 Flash (generation) + Gemini 3.1 Flash Lite (review)
- **Search**: Vertex AI Search (Enterprise) with 225+ indexed textbook PDFs
- **Async**: Cloud Tasks → Cloud Run pipeline
- **Storage**: Firestore (job tracking) + GCS (documents)

## API Endpoints

| Method   | Endpoint                              | Description                 |
| -------- | ------------------------------------- | --------------------------- |
| `GET`    | `/health`                             | Liveness probe              |
| `POST`   | `/api/v1/generate`                    | Create async generation job |
| `GET`    | `/api/v1/generations/{id}`            | Poll job status/result      |
| `GET`    | `/api/v1/game-types`                  | List supported game types   |
| `POST`   | `/api/v1/users/{id}/documents/upload` | Upload user document        |
| `GET`    | `/api/v1/users/{id}/documents`        | List user documents         |
| `POST`   | `/api/v1/admin/documents/upload`      | Upload system document      |
| `GET`    | `/api/v1/admin/documents`             | List system documents       |
| `DELETE` | `/api/v1/admin/documents/{id}`        | Delete system document      |

Full OpenAPI spec: `docs/openapi.json`

## Quick Start

```bash
# Install
conda activate AIservice
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with ENV=develop

# Run locally
uvicorn src.main:app --reload

# Generate content (local async mode)
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "topic": "Đạo hàm", "game_types": ["quiz"], "num_questions": 5}'
```

## Local Docker

```bash
# Prerequisites
gcloud auth application-default login   # GCP credentials

# Build & run
docker compose up --build -d

# Check status
docker compose logs -f api
curl http://localhost:8000/health

# Stop
docker compose down
```

Container exposes port `8000`, mounts `.env` + `.env.develop` and GCP ADC credentials.

## Testing

```
notebooks/tests/
├── test_accuracy.ipynb          # Content quality / STEM accuracy
├── test_performance.ipynb       # Latency & throughput benchmarks
├── test_e2e_docker.ipynb        # E2E tests against local Docker
├── test_vertex_search.ipynb     # Vertex AI Search integration
└── test_graph_pipeline.ipynb    # LangGraph pipeline unit tests
```

Run notebooks with the `AIservice` conda kernel.

## Cloud Deployment

```bash
# Build and deploy to Cloud Run
./scripts/deploy.sh
```

Requires `--no-allow-unauthenticated` — callers need `roles/run.invoker`.

## Project Structure

```
src/
├── main.py                    # FastAPI app
├── api/
│   ├── errors.py              # Error handlers
│   ├── routes/                # API endpoints
│   └── schemas/               # Pydantic models
├── config/                    # Settings, constants
├── graph/
│   ├── builder.py             # LangGraph pipeline
│   ├── state.py               # AgentState
│   └── nodes/                 # supervisor, math_agent, reviewer, formatter
└── services/                  # LLM, Firestore, Vertex Search, GCS
```
