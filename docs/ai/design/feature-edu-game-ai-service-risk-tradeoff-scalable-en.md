```markdown
---
phase: design
title: Risk & Trade-off Analysis (Production + Scalable)
description: Analysis of foundational risks, architectural trade-offs, and optimal approaches for production deployment and sustainable scaling
---

# Risk & Trade-off Analysis (Production + Scalable)

## Objective

This document focuses on foundational risks and architectural decisions with the following goals:

- Deploy a stable production system
- Scale users and data sustainably
- Control costs and reduce high-risk lock-in
- Prioritize optimal approaches by impact/effort

> This document does not use an MVP perspective.

## 1) Identity & Authentication

### Context

AI Service is an **internal service** — it does not receive requests directly from end-users. The call flow is:
```

End User → Upstream Service (handles user business logic, auth) → AI Service → Game Service

```

Upstream service has already authenticated the user (login, session, JWT...). AI Service only needs to **verify that the request comes from a valid upstream** and that the **accompanying user_id is trustworthy**.

### Risks

If AI Service is exposed publicly without verification → anyone can call the API with any `user_id`. However, since this is an internal service, the main risk is **service-to-service trust**, not user-facing auth.

### Options

| Option | Description                               |         Effort | Suitable For                                  |
| ------ | ----------------------------------------- | -------------: | --------------------------------------------- |
| A      | Firebase Auth + JWT (user-facing)         |       2-3 days | When AI Service exposes directly to client    |
| B      | API key per user                          |         1 day  | When per-user tracking is needed at AI layer  |
| C      | Identity Platform (OIDC/SAML)             |       5-7 days | Enterprise multi-tenant                       |
| **D**  | **Service-to-service auth + trusted user_id** | **0.5-1 day** | **Internal service pattern (current case)** |

### Analysis of Option D (Service-to-service trust)

Since AI Service only receives requests from upstream service that has already authenticated the user:

1. **Service-to-service auth:** Upstream calls AI Service with `X-Internal-API-Key` (shared secret) or Google Cloud IAM (Cloud Run service-to-service auth — recommended, zero secret management).
2. **Trusted user_id:** Upstream has verified user → passes `user_id` in request body. AI Service trusts this value because the source was verified in step 1.
3. **Admin operations:** Upstream service calls with flag `scope: "system"` + service auth. No separate `X-Admin-Key` needed if upstream has already authorized admin.

**Cloud Run IAM mechanism (recommended):**

```

# Upstream service account is granted permission to invoke AI Service

gcloud run services add-iam-policy-binding ai-service \
 --member="serviceAccount:upstream-svc@project.iam.gserviceaccount.com" \
 --role="roles/run.invoker"

```

→ Only upstream service can call AI Service. No API key needed. No JWT verification in code.

### Optimal Recommendation

**Choose Option D (Service-to-service auth + trusted user_id)**

- AI Service doesn't need to build auth layer for end-users
- Use Cloud Run IAM for service-to-service → zero code, native GCP
- `user_id` is a trusted value from upstream, AI Service uses directly to scope data
- If AI Service needs to expose public later → upgrade to Option A (Firebase Auth)

## 2) Request Lifecycle: Async-first

### Context

The actual flow is:

```

End User → Upstream Service → AI Service (heavy processing) → Game Service

````

AI Service is in the middle of the pipeline, generation processing takes time (query AI Search + LLM call + review loop). Upstream doesn't wait for sync response.

### Risks with Sync

- HTTP timeout between upstream ↔ AI Service (Cloud Run default 300s)
- Upstream must hold connection waiting → blocks resources
- Network hiccup = lose all results
- No progress tracking

### Options

| Option | Description                     |       Effort | Scalability    |
| ------ | ------------------------------- | -----------: | -------------- |
| **A**  | **Async + Polling**             | **2-3 days** | **High**       |
| B      | Async + Webhook/Callback        |     3-4 days | High           |
| C      | SSE Streaming                   |     4-5 days | Medium-High    |
| D      | Hybrid: sync for small, async for large | 3 days | High       |

### Analysis: Why Async-first (Option A)

Since the flow is service-to-service (not user directly waiting for HTTP):

1. **POST /api/v1/generate** → returns immediately `{ request_id, status: "processing" }` (< 1s)
2. AI Service processes in background (Cloud Tasks or background thread in Cloud Run)
3. Upstream/Game Service polls `GET /api/v1/generations/{request_id}/status` for results
4. When complete → status = `"completed"`, result saved to Firestore, returned via GET

**Extension to Option B (Webhook) if needed:**

- Upstream registers `callback_url` when calling generate
- AI Service POSTs result to `callback_url` when complete
- Reduces polling overhead, but upstream needs to implement webhook receiver

### Detailed Flow

```mermaid
sequenceDiagram
    participant U as Upstream Service
    participant AI as AI Service
    participant CT as Cloud Tasks
    participant FS as Firestore
    participant GS as Game Service

    U->>AI: POST /generate {user_id, topic, game_types...}
    AI->>FS: Save job {request_id, status: processing}
    AI->>CT: Enqueue generation task
    AI-->>U: 202 {request_id, status: processing}

    CT->>AI: Execute generation (LangGraph)
    AI->>FS: Save result {status: completed, content: ...}

    U->>AI: GET /generations/{request_id}/status
    AI->>FS: Read result
    AI-->>U: 200 {status: completed, content: ...}

    U->>GS: Forward game content
````

### Optimal Recommendation

**Choose Async-first (Option A)**

- All generation requests are async, no exceptions
- Use Cloud Tasks to dispatch jobs → reliable, has retry, has dead-letter queue
- LangGraph checkpoint ensures resume if Cloud Run instance is killed
- If more real-time is needed → add webhook (Option B) later

## 3) Vertex AI Search Data Strategy

### Risks

Single Data Store for all user + system docs can become a bottleneck when data/queries increase significantly; index delay affects UX.

### Options

| Option | Description                                            |   Effort | When to Apply                              |
| ------ | ------------------------------------------------------ | -------: | ------------------------------------------ |
| A      | Single Data Store + monitoring                         |        0 | Small-medium scale                         |
| B      | Partition Data Store by tenant/group                   | 3-5 days | When users/docs scale high                 |
| C      | Hybrid retrieval (AI Search + extracted text fallback) | 5-7 days | When reducing index delay impact is needed |

### Optimal Recommendation

**Choose Option A (Single Data Store) — current development phase**

- Simple, fast deployment, low ops
- Sufficient for development and early users
- **Migration path:** When data scales high → switch to Option B (partition). Code already abstracts `data_store_id` via config → switch doesn't require business logic changes
- **Fallback for index delay:** Consider partial Option C when needed (extract text on upload → use as temporary context if AI Search hasn't indexed yet)

## 4) Cost Control (Production)

### Risks

Costs increase rapidly with query volume, tokens, and retry loops; without guardrails, very easy to exceed operational budget.

### Options

| Option | Description                            | Impact                         |
| ------ | -------------------------------------- | ------------------------------ |
| A      | Flash-first policy (Pro conditionally) | Significantly reduces LLM cost |
| B      | Response caching by request signature  | Reduces repeated model calls   |
| C      | Budget watchdog + degrade mode         | Avoids bill shock              |
| D      | Context caching for system docs        | Reduces input token cost       |

### Optimal Recommendation

**Deploy A + B + C simultaneously**, add D when traffic stabilizes.

- **A (Flash-first):** Apply immediately in code — choose Flash as default model, Pro only when complex reasoning is needed
- **B (Response cache):** Implement early because low-effort, high-impact — hash request params → check Firestore before calling LLM
- **C (Budget watchdog):** Setup Cloud Billing alert immediately when deploying to GCP. Threshold $15 → warning, $22 → degrade mode
- **D (Context caching):** Add when actual traffic statistics are available to evaluate ROI

> **Note:** No specific cost statistics yet because system is in development phase. Estimated figures will be updated after running PoC and having actual data.

## 5) Data Layer: Firestore vs SQL

### Risks

Firestore is suitable for operational CRUD but limited for analytics/complex queries as product evolves.

### Options

| Option | Description                 |   Effort | Scalability |
| ------ | --------------------------- | -------: | ----------- |
| A      | Firestore-only              |        0 | Medium      |
| B      | Cloud SQL PostgreSQL        | 3-5 days | High        |
| C      | Firestore + BigQuery export | 2-3 days | High        |
| D      | AlloyDB                     |  5+ days | Very high   |

### Optimal Recommendation

**A first, C as soon as analytics is needed**.

- Keep Firestore for operational simplicity
- Add BigQuery for reporting/BI
- Apply repository pattern to avoid lock-in at business logic layer

## 6) Platform Lock-in

### Risks

Highest lock-in is in: Vertex AI Search and Gemini-specific capabilities.

### Options

| Option | Description                  |   Effort | Trade-off                          |
| ------ | ---------------------------- | -------: | ---------------------------------- |
| A      | Full provider abstraction    | 2-3 days | High flexibility, added complexity |
| B      | All-in GCP                   |        0 | Fastest, high lock-in              |
| C      | Abstract critical paths only | 1-2 days | Good balance                       |

### Optimal Recommendation

**Choose Option C**

- Abstract `SearchProvider` + `LLMProvider`
- Keep GCS/Firestore/Cloud Run native to avoid over-engineering

## 7) User-first Re-ranking Quality

### Risks

Absolute prioritization of user documents can reduce quality if user docs are noisy/poor quality.

### Options

| Option | Description                    | Quality     |
| ------ | ------------------------------ | ----------- |
| A      | Hard source-first (user first) | Medium      |
| B      | Threshold by relevance         | High        |
| C      | Blended ranking                | Medium-High |
| D      | Quality-weighted re-ranking    | Highest     |

### Optimal Recommendation

**Choose Option D**

Combined score `relevance_score * source_weight` to balance personalization and accuracy.

## 8) Document Lifecycle & Versioning

### Risks

Lack of versioning/deletion workflow makes traceability difficult, hard to rollback, hard to ensure consistency when updating documents.

### Optimal Recommendation

- Add `version`, `replaced_by`, `deleted_at`, `content_hash` to `DocumentRecord`
- Apply soft delete + lifecycle cleanup
- Enable duplicate detection by `content_hash`

## 9) API Contract Hardening

### Additions needed for production-ready

1. Pagination for list endpoints (`limit`, `cursor`)
2. Health/readiness endpoints
3. Idempotency key for generate
4. Rate limiting per user and per API key

## 10) Reliability & Degradation Strategy

### Risks

When downstream services fail (AI Search/LLM/Firestore), system lacks degrade/fallback mechanism.

### Optimal Recommendation

- Add circuit breaker in service layer
- Fallback by situation:
  - AI Search fails → fallback to extracted text (if available)
  - Pro fails → auto-switch to Flash
  - Firestore fails → still serve response, log retry persistence
- Return structured errors + `retry-after`

---

## Implementation Priority Matrix

| Priority | Item                                           | Impact                |    Effort |
| -------- | ---------------------------------------------- | --------------------- | --------: |
| P0       | Cloud Run IAM (service-to-service auth)        | Very high             | 0.5-1 day |
| P0       | Async-first generation (Cloud Tasks + polling) | Very high             |  2-3 days |
| P0       | Rate limiting + quota guardrail                | Very high             |  1-2 days |
| P0       | Health/readiness + pagination                  | High                  |  1-2 days |
| P1       | Flash-first + response cache + budget watchdog | High                  |  1-2 days |
| P1       | Quality-weighted re-ranking                    | High                  |     1 day |
| P1       | Idempotency + document versioning              | High                  |  2-3 days |
| P2       | Provider abstraction (critical paths)          | Medium-High           |  1-2 days |
| P2       | Circuit breaker + fallback                     | Medium-High           |  2-3 days |
| P3       | Firestore → BigQuery analytics pipeline        | Medium                |  1-2 days |
| P3       | Partitioned Data Store strategy                | High (at large scale) |  3-5 days |

## Conclusion

The optimal approach to ship product while remaining scalable:

1. **Service-to-service auth (Cloud Run IAM)** — AI Service is internal, no user-facing auth needed
2. **Async-first lifecycle** — all requests are async via Cloud Tasks, upstream polls for results
3. **Add cost + rate limiting guardrails**
4. **Optimize quality re-ranking by score (not hard source-first)**
5. **Selective abstraction design to reduce highest lock-in**

This roadmap maintains deployment speed without sacrificing production foundation.

```

```
