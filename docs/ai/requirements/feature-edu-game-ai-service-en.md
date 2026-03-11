```markdown
---
phase: requirements
title: Requirements & Problem Understanding
description: Clarify the problem space, gather requirements, and define success criteria
---

# Requirements & Problem Understanding

## Problem Statement

**What problem are we solving?**

### Context

Creating content for educational games still relies entirely on humans — teachers or content creators must manually write each question, answer, and explanation. This process is:

- **Time-consuming:** Creating 100 quality Quiz questions for one chapter takes days.
- **Hard to scale:** Each subject, chapter, and teacher has their own materials.
- **Inconsistent quality:** Especially for calculation-based questions where answers may be incorrect.
- **Lacking variety:** Difficult to create multiple game types (Quiz, Flashcard, Adventure, Matching...) from the same source documents.

### Core Problem

We need an **AI Service** capable of:

1. **Maintaining a foundation document repository** (system/shared) managed by Admin — textbooks, standard curricula, reference materials — so the system works even when users haven't uploaded anything.
2. **Receiving user documents** (lesson plans, curricula, lecture slides, syllabi — PDF/DOCX/PPTX) — adding to personal knowledge sources.
3. **Reading and indexing** documents via Vertex AI Search (both system docs and user docs).
4. **Generating educational game content** (JSON) based on documents — prioritizing user docs if available, falling back to system docs if not.

All game types are **Q&A-based** at the foundation layer (question-answer, concepts, matching...). The system generates **educational content items** → formats them according to the corresponding **game template**.

### Two Document Sources

| Source          | Managed By | Purpose                                                                           | GCS prefix        |
| --------------- | ---------- | --------------------------------------------------------------------------------- | ----------------- |
| **System docs** | Admin      | Foundation document repository (textbooks, standard curricula) — always available | `system/`         |
| **User docs**   | User       | Personal documents (lesson plans, slides, personal syllabi)                       | `user/{user_id}/` |

### Who is Affected?

- **Admin:** Manages foundation document repository (system docs) — textbooks, standard curricula, reference materials.
- **Teachers:** Upload their lesson plans/curricula → receive automatic game content. Or use system docs if they don't have their own materials.
- **Content creators:** Create educational games quickly from available documents (system or personal).
- **Students:** Have diverse learning games that closely follow lectures.
- **Game development team:** Has rich, JSON-standardized content sources.

### Why GCP + Vertex AI Search?

Team **has no existing infrastructure** → needs 100% Managed Services:

- **Vertex AI Search** (Discovery Engine) — completely replaces self-built RAG pipeline (no need for pgvector, chunking, embedding).
- **Gemini** Native Agentic + Code Execution → significantly reduces code needed.
- GCP project `green-mercury-485016-n1` — APIs already enabled, need to setup resources (Data Store, bucket, Firestore, Service Account).

## Goals & Objectives

**What do we want to achieve?**

### Primary Goals

1. **Dual document sources:** System docs (Admin managed, always available) + User docs (personal, optional). Users can generate games immediately without uploading — using system docs.
2. **User-centric document management:** Each user uploads their documents → system indexes and scopes queries per user. GCS bucket structure: `user/{user_id}/{YYYY-MM-DD}/{session_id}/`.
3. **Flexible game type system:** All game types are Q&A-based → system generates **content items** (questions, concepts, facts) → **game template** transforms into specific format. Adding new game type = adding template schema + prompt.
4. **LangGraph as the sole core orchestration** for all business logic. Extending business logic = adding nodes/edges to graph.
5. **Vertex AI Search replaces RAG pipeline** — upload docs → Data Store auto-indexes → query via `VertexAISearchRetriever`. Zero custom indexing code.
6. **Support 3 input formats:** PDF, DOCX, PPTX.
7. **Feedback loop in LangGraph:** Supervisor → Agent → Reviewer → reject → retry (max 3 times).

### Secondary Goals

- LangGraph graph extensible: specialized agents (Math, Story, Visual, Structure) as separate nodes with conditional routing.
- REST API for Game Client.
- Structured logging via GCP Cloud Logging.

### Non-Goals (Out of Current Scope)

- ❌ Build separate RAG pipeline (using Vertex AI Search).
- ❌ Setup Vector DB (pgvector, Chroma, etc).
- ❌ Game Client/Frontend.
- ❌ Complex user auth (OAuth2, JWT) — AI Service is internal, using Cloud Run IAM service-to-service auth.
- ❌ Real-time streaming.
- ❌ User tiers / pricing tiers — monitor usage first, consider tiers later.

### 4-Pillar Strategy

The system follows a **4-Pillar Strategy** to handle different educational content types optimally:

| Pillar       | Data Type             | Subjects                         | Key Challenge                      | Solution                               | Phase   |
| ------------ | --------------------- | -------------------------------- | ---------------------------------- | -------------------------------------- | ------- |
| **Pillar 1** | Logic & Computational | Math, Physics, Chemistry         | LLM calculates incorrectly         | **Math Agent + Python Code Execution** | Phase 1 |
| **Pillar 2** | Narrative & Semantic  | Literature, History, Civics      | Context loss, causal relationships | **Story Agent + GraphRAG**             | Phase 2 |
| **Pillar 3** | Spatial & Visual      | Geography, Biology, Technology   | Info in images/diagrams            | **Visual Agent + Multimodal LLM**      | Phase 3 |
| **Pillar 4** | Structured & Taxonomy | English grammar, Chemical tables | Table/list structure breaking      | **Structure Agent + Table Extraction** | Phase 4 |

Each data type requires **specialized handling** — a generic agent cannot solve all problems optimally.

## User Stories & Use Cases

**How will users interact with the solution?**

### User Stories

**US-1: Admin uploads foundation documents (System docs)**

> As an **Admin**, I want to upload Math 11 textbook, Physics 12, Chemistry 10 (PDF/DOCX/PPTX) to the shared document repository (system docs) → so all users can generate games from them immediately without uploading anything.

**US-2: Admin manages system docs**

> As an **Admin**, I want to view list, delete, add documents in the system docs repository → manage quality of foundation document sources.

**US-3: User generates game without uploading (using system docs)**

> As a **Teacher**, I don't have my own lesson plan yet but want to generate 10 Quiz questions for "Derivatives" chapter in Math 11 → system uses available textbook (system docs) → returns JSON game content.

**US-4: Upload personal documents**

> As a **Teacher**, I want to upload my Math 11 lesson plan (PDF/DOCX/PPTX) → system indexes the document into my workspace → I can generate game content from it.

**US-5: Generate Quiz from personal curriculum**

> As a **Teacher**, I want to select "Derivatives" chapter from uploaded documents → generate 20 multiple choice questions (answers calculated via Code Execution) → returns JSON for game engine.

**US-6: Generate Flashcard from lecture slides**

> As a **Content Creator**, I want to upload Physics "Dynamics" slide → generate Flashcards (front: formula, back: explanation + example) from slide content.

**US-7: Generate Adventure Q&A game** _(Phase 2)_

> As a **Game Developer**, I want to generate content for adventure game: narrative intro → branching Q&A → player chooses correct answer to proceed → all based on Chemistry documents (system or user docs).

**US-8: Generate multiple game types simultaneously**

> As a **Teacher**, I want to select 1 chapter → generate simultaneously Quiz + Flashcard + Fill-in-blank + Matching → receive all in 1 JSON response.

**US-9: Quality control**

> As a **QA Engineer**, I want each question to go through Reviewer node in LangGraph, ensuring error rate < 2%.

**US-10: Customize parameters**

> As a **User**, I want to specify: quantity, difficulty level, game type, chapter/topic, to receive output matching my needs.

### Key Workflow
```

Flow A — Admin adds system docs:

1.  Admin: POST /api/v1/admin/documents/upload { file, subject, grade }
    → Upload GCS: gs://bucket/system/{YYYY-MM-DD}/{session_id}/{filename}
    → Import Vertex AI Search Data Store (metadata: user_id="**system**", subject, grade)
    → Auto-index (~10-15 minutes)

Flow B — User uploads personal documents:

1.  User uploads document (PDF/DOCX/PPTX):
    → API receives file → validate format
    → Upload GCS: gs://bucket/user/{user_id}/{YYYY-MM-DD}/{session_id}/{filename}
    → Import into Vertex AI Search Data Store (metadata: user_id, upload_date, subject)
    → Auto-index (~10-15 minutes)

Flow C — Generate game content:

1.  User: POST /api/v1/generate {
    user_id, topic/chapter, game_types[], difficulty, num_questions,
    doc_scope: "user" | "system" | "all" (default: "all")
    }

2.  LangGraph graph runs:
    a. Supervisor: receives request → analyzes content type → routes to specialized agent
    (Math → Math Agent, History → Story Agent, etc.)
    b. Specialized Agent (based on 4-Pillar Strategy):
    - **Math Agent**: queries VertexAISearchRetriever + Code Execution for calculations
    - **Story Agent** (Phase 2): queries + GraphRAG for timeline/causality
    - **Visual Agent** (Phase 3): queries + Multimodal Vision for images
    - **Structure Agent** (Phase 4): queries + Table extraction for structured data
      Doc scope filtering:
    - doc_scope="user": filter user_id only
    - doc_scope="system": filter user_id="**system**" only
    - doc_scope="all": query both → user-first re-ranking
      c. Reviewer (Gemini Flash): checks quality, grounding
      d. Fail → feedback loop to Supervisor (max 3 times)
      e. Formatter: receives content items + game_types[]
      → transforms according to game template
      → outputs Pydantic-compliant JSON

3.  Save to Firestore → return API response

```

### Game Types — Q&A Foundation

All game types are based on **educational content items** at the base layer:

| Game Type         | Q&A Nature                      | Output Structure                                                |
| ----------------- | ------------------------------- | --------------------------------------------------------------- |
| **Quiz**          | Question + 4 options + 1 correct | `{ question, options[], correct_index, explanation }`           |
| **Flashcard**     | Concept pair (front/back)       | `{ front, back, tags[] }`                                       |
| **Fill-in-blank** | Sentence with blanks + answers  | `{ template, blanks[], explanation }`                           |
| **Adventure Q&A** | Narrative + branching questions | `{ narrative, question, choices[], correct_path, consequence }` |
| **Matching**      | Pairs to connect                | `{ pairs[{left, right}], category }`                            |
| **True/False**    | Statement + boolean answer      | `{ statement, is_true, explanation }`                           |
| **Ordering**      | Items to arrange                | `{ items[], correct_order[], context }`                         |

**Phase 1:** Quiz, Flashcard, Fill-in-blank (validated). Adding game types = adding Pydantic schema + formatter prompt. No changes to LangGraph graph needed.
**Phase 2:** Timeline, True/False, Matching (for Story Agent).
**Phase 3:** Map labeling, Diagram annotation (for Visual Agent).
**Phase 4:** Grammar drill, Pattern matching (for Structure Agent).

### Edge Cases

- Document doesn't have enough content for requested questions → return partial + warning
- Upload file with wrong format → 400 + supported formats list
- Vertex AI Search not finished indexing → 409 "Document still indexing"
- User queries another user's documents → reject (scope enforcement)
- User has no docs + doc_scope="user" → 400 "No user documents found. Use doc_scope=system or all."
- System docs empty + doc_scope="system" → 400 "No system documents available"
- System docs empty + doc_scope="all" + user has docs → still succeeds (uses user docs)
- PPTX with only images, little text → warning "Insufficient text content"
- Code Execution timeout → retry with simplified prompt, max 3 times
- Duplicate questions → dedup check in Formatter

## Success Criteria

**How will we know when we're done?**

### Functional

- [ ] Admin uploads system docs → GCS `system/` folder → AI Search indexes successfully
- [ ] User uploads personal docs → GCS `user/{user_id}/` folder → AI Search indexes successfully
- [ ] Generate with doc_scope="system" → uses only system docs
- [ ] Generate with doc_scope="user" → uses only user docs
- [ ] Generate with doc_scope="all" (default) → uses both, user-first (user docs ranked first in context)
- [ ] Generate without uploading → uses system docs → succeeds
- [ ] User documents scoped: query only returns results from that user's documents
- [ ] Generate request → valid JSON output for 3 Phase 1 game types
- [ ] Game template system: adding new game type doesn't require modifying graph
- [ ] JSON 100% conforms to Pydantic schema
- [ ] Reviewer rejects → LangGraph feedback loop → retry → pass
- [ ] LangGraph checkpoint persistence works

### Quality

- [ ] Accuracy ≥ 98% on 100-question test set
- [ ] Grounded (adheres to documents in scope — user docs and/or system docs — via Vertex AI Search), no hallucination
- [ ] Content items match requested game type

### Performance

- [ ] < 60s for 10 questions, < 5 minutes for 50 questions
- [ ] ≥ 10 concurrent requests on Cloud Run
- [ ] Vertex AI Search query < 2s
- [ ] Document indexing < 15 minutes for 50MB file

### Cost

- [ ] ≤ $25/month total cost

## Constraints & Assumptions

**What limitations do we need to work within?**

### Technical Constraints

- **Cloud:** 100% GCP — project `green-mercury-485016-n1` (APIs enabled, need to setup resources)
- **LLM:** Gemini Pro/Flash (Vertex AI)
- **Knowledge:** Vertex AI Search (Discovery Engine) — zero custom RAG
- **Orchestration:** LangGraph (sole core for business logic)
- **Runtime:** Python 3.12+, FastAPI, LangChain
- **Database:** Firestore (serverless, JSON-native)
- **Deploy:** Cloud Run
- **Input formats:** PDF, DOCX, PPTX

### Business Constraints

- Budget: ≤ $25/month
- Team: small, prioritize managed services
- Timeline: 2 weeks for Phase 1, 8-9 weeks for complete 4-Pillar implementation

### Assumptions

- Vertex AI Search handles Vietnamese PDF/DOCX/PPTX well
- Vertex AI Search supports metadata filtering (scope per user)
- Gemini Code Execution supports SymPy/NumPy
- `VertexAISearchRetriever` integrates with LangGraph
- Game Client team adapts to JSON schema defined by AI service
- Output in Vietnamese, difficulty determined by AI

### Privacy & Data Consent

- **User docs are private by default:** Only the uploading user can query (scope enforcement via metadata filter `user_id`).
- **System docs are shared documents:** All users can access. Admin is responsible for quality and copyright.
- **Consent policy:** When uploading, users are asked to consent to allow their documents to be used for system improvement (improve retrieval quality, prompt tuning).
  - **Consent:** Documents may be used to evaluate and improve retrieval/generation quality (no model training).
  - **No consent:** Documents are only stored in GCS + indexed in AI Search to serve that user. Not used for any other purpose.
- **User documents not used for training or fine-tuning models** (Gemini is a managed API, no custom training).
- **Data retention:** User documents inactive > 6 months → consider deletion. System docs (textbooks, curricula) are long-term → no auto-delete.
- **Document classification:** System needs to evaluate document nature (long-term vs temporary) based on metadata (subject, scope) to apply appropriate retention policy.

## Questions & Open Items

**What do we still need to clarify?**

### Decided

1. GCP project `green-mercury-485016-n1` — setup from scratch
2. 100% GCP managed services
3. Vertex AI Search replaces RAG pipeline
4. LangGraph = sole core for business logic
5. Firestore for database (serverless)
6. JSON schema defined by AI service
7. GCS bucket: `user/{user_id}/{YYYY-MM-DD}/{session_id}/` — user isolation
8. GCS bucket: `system/{YYYY-MM-DD}/{session_id}/` — admin-managed shared docs
9. Input: PDF + DOCX + PPTX
10. All game types = Q&A-based, extensible template system
11. Vietnamese language, async-first API (Cloud Tasks + polling)
12. Dual doc sources: system docs (admin) + user docs (personal)
13. `doc_scope="all"` uses user-first: query both sources → post-retrieval re-ranking, user docs ranked before system docs
14. Privacy & Data Consent: users consent to allow documents to improve system, not used for model training
15. User tiers (free/premium) = non-goal for Phase 1, monitor usage first
16. Data retention: user docs > 6 months inactive → consider deletion. System docs (textbooks) = long-term
17. Rate limiting: defer, calculate after having actual usage data
18. Max documents per user: no limit yet, monitor usage → consider quota per tier if needed
19. Vertex AI Search query quota: monitor usage, implement fallback/rate limit if exceeds quota

### Need to Validate via PoC

20. Vertex AI Search + Vietnamese PDF/DOCX/PPTX: quality of extractive answers
21. Vertex AI Search metadata filtering: scope query per user_id
22. Gemini Code Execution: sandbox supported libraries
23. Vertex AI Search pricing for Data Store + query volume
24. `VertexAISearchRetriever` + metadata filter + LangGraph integration

### GCP APIs (already enabled)

All APIs have been enabled. See detailed resource setup in Implementation Guide → GCP Setup section.

| API                              | Service          | Purpose                       |
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

### Future Roadmap (LangGraph graph extension)

| Phase       | Focus                                                                            | New LangGraph Node    | Additional GCP Service |
| ----------- | -------------------------------------------------------------------------------- | --------------------- | ---------------------- |
| **Phase 1** | Q&A-based games (Quiz, Flashcard, Fill-blank) + Dual doc sources (System + User) | Math Agent + Formatter | Code Execution, AI Search |
| **Phase 2** | Narrative games (Adventure, Story-driven)                                        | Story Agent           | Context Caching        |
| **Phase 3** | Visual games (Image-based, Diagram)                                              | Visual Agent          | Gemini Vision          |
| **Phase 4** | Structured games (Table, Classification)                                         | Table Agent           | AI Search (structured) |

---

> [!Note] Decisions from User Notes have been integrated into main content:
>
> - GCS bucket: `system/` (admin docs) + `user/{user_id}/` (user docs). AI Search metadata: `user_id="__system__"` / `user_id="{user_id}"`.
> - APIs enabled. Rate limit, retention, quota, privacy → recorded in "Decided" #13-19.
> - User tiers (free/premium) = non-goal for Phase 1.
```
