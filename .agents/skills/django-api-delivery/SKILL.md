---
name: django-api-delivery
description: Deliver Django and DRF API work for this RAVID assessment. Use when implementing or reviewing authentication, serializers, request validation, views, models, routes, or API contracts so the agent stays aligned with the locked stack, thin-view design, documented payloads, the exact assessment endpoints, and explicit validation behavior.
---

# Django API Delivery

## Purpose

Use this skill for Django and DRF implementation work in the assessment: project wiring, apps, routing, models, serializers, auth endpoints, the document upload endpoint, the chat query endpoint, and the task-status endpoint. Use the pipeline and retrieval skills for the heavy RAG work behind these endpoints.

## Read Before Work

1. `.agents/MISTAKE.md`
2. `.agents/guidelines/ai-programming-guidelines.md`
3. `.agents/references/assessment-decisions.md`
4. The active `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}`
5. `docs/02-features/<NN-name>/test_matrix.md`

## Scope

Use for:

- project setup and settings (DRF, SimpleJWT, Celery wiring)
- apps and URL routing (`apps/documents`, `apps/rag`, plus accounts/auth)
- models and migrations
- serializers and request validation
- auth endpoints (register, login, JWT issuance)
- permissions and ownership enforcement
- the document upload endpoint contract
- the chat query endpoint contract
- the task-status API response contract

## Endpoints (verbatim from the assessment PDF)

Match these paths and shapes exactly:

- `POST /api/register/` — JSON `{email, password}` -> `201 {message, user_id}` | `400 {error}`
- `POST /api/login/` — JSON `{email, password}` -> `200 {message, token}` | `401 {error}`
- `POST /api/documents/upload/` — multipart form-data, field `file`; JWT -> `202 {message, document_id, task_id}` | `400 {error}`
- `GET /api/documents/status/?task_id=<id>` — JWT -> `{task_id, status: PROCESSING|SUCCESS|FAILURE, ...}`
- `POST /api/chat/query/` — JSON `{query}`; JWT -> `200 {answer, tokens_consumed}`
- Bonus: chat continuation via `chat_id`; SSE streaming.

## Rules

- Match the assessment endpoint paths exactly (the list above). Earlier guesses were wrong; these are authoritative.
- Use serializers for request validation; do not validate ad hoc in views.
- Keep views thin and orchestration explicit. Heavy work (ingestion, embedding, retrieval, LLM calls) belongs in Celery tasks or service functions, not in the request-response path.
- Use DRF and SimpleJWT conventions instead of custom auth mechanisms. Missing or invalid JWT -> `401`.
- Enforce ownership with an owner FK. Cross-user access to a document, task, or vector returns `404` (not `403`) to avoid leaking existence (M-005 is the data-layer counterpart; this is the API-layer counterpart).
- Upload validation: allow `.pdf .txt .md` only, max 10 MB; reject others with `400 {"error": "..."}`.
- Use the single-field error envelope everywhere: `{"error": "<message>"}`.
- Do not silently accept ambiguous or malformed payloads (M-003).
- Never log raw document text, JWTs, OpenRouter keys, or embedding keys (M-008).
- Document any response shape that goes beyond the PDF examples in the OpenSpec change and `docs/01-architecture/api_contract.yaml`.

## Required Checks

- Relevant mistake rules reviewed before coding
- OpenSpec change (proposal/design/tasks) updated when behavior changes
- Tests added for validation, auth (401), and ownership (404-not-403) behavior
- Upload type/size rejection tests (400)
- Error envelope shape verified on every error path
- README and `api_contract.yaml` updated when the public contract changes

## Output

When this skill is used, the work should leave behind:

- updated code (thin views, serializers, models, routes)
- updated OpenSpec change if the contract changed
- updated `docs/02-features/<NN-name>/test_matrix.md` if coverage changed
- updated README / `api_contract.yaml` if the public contract changed
- validation evidence
