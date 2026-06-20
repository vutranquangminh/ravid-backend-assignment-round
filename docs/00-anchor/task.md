# Delivery Task Breakdown

## Goal

Break the RAVID RAG chatbot backend assessment into a practical execution order that supports
fast delivery and clear validation. Each numbered workstream maps 1:1 to a delivery feature
workspace under `docs/02-features/<NN-name>/` and to a matching OpenSpec change under
`openspec/changes/<NN-name>/`. OpenSpec owns `proposal.md`, `design.md`, and `tasks.md` for each
slice; `docs/02-features/<NN-name>/` owns the QA and delivery artifacts
(`test_matrix.md`, `pr-review.md`, `validation-report.md`, `pull_request.md`). Each slice is one
git branch `feature/NN-<scope>` and one PR into merge-only `main`.

## Workstreams

### 00. Foundation: Branch And PR Workflow

- Branch: `feature/00-foundation-branch-pr-workflow`
- Feature workspace: `docs/02-features/00-foundation-branch-pr-workflow/`
- OpenSpec change: `openspec/changes/00-foundation-branch-pr-workflow/`
- Establish the `.agents/` operating system, the anchor and architecture docs, the hybrid
  OpenSpec + branch/PR discipline, the locked decisions, and the validation scripts.
- No product or Django code in this branch.

### 01. Foundation: Django + LangChain Bootstrap

- Branch: `feature/01-foundation-django-langchain-bootstrap`
- Feature workspace: `docs/02-features/01-foundation-django-langchain-bootstrap/`
- OpenSpec change: `openspec/changes/01-foundation-django-langchain-bootstrap/`
- Initialize the Django project structure (apps `documents`, `rag`, plus accounts/core).
- Configure PostgreSQL, DRF, JWT auth package, Celery, and Redis.
- Wire the LangChain stack: document loaders, `RecursiveCharacterTextSplitter`, Chroma vector
  store, and local HuggingFace embeddings (`all-MiniLM-L6-v2`).
- Define the environment and settings strategy and `.env.example`.

### 02. Authentication: Register, Login, JWT

- Branch: `feature/02-authentication-register-login-jwt`
- Feature workspace: `docs/02-features/02-authentication-register-login-jwt/`
- OpenSpec change: `openspec/changes/02-authentication-register-login-jwt/`
- Implement `POST /api/register/` returning `201` with `user_id`.
- Implement `POST /api/login/` returning `200` with a JWT `token`.
- Protect document and chat routes with JWT; keep register and login public.
- Validate auth error behavior (`400` on bad registration, `401` on bad login / missing token).
- Seed the per-user credit balance at registration.

### 03. Document Upload: PDF, TXT, MD

- Branch: `feature/03-document-upload-pdf-txt-md`
- Feature workspace: `docs/02-features/03-document-upload-pdf-txt-md/`
- OpenSpec change: `openspec/changes/03-document-upload-pdf-txt-md/`
- Define the owner-scoped document model and metadata.
- Implement `POST /api/documents/upload/` accepting `multipart/form-data` with a `file` field.
- Validate file type (`.pdf`, `.txt`, `.md` only) and size (max 10 MB); reject with `400` and
  the error envelope.
- Persist the document, enqueue the ingestion task, and return `202` with `document_id` and `task_id`.

### 04. Ingestion Pipeline: Chunk, Embed, Chroma

- Branch: `feature/04-ingestion-pipeline-chunk-embed-chroma`
- Feature workspace: `docs/02-features/04-ingestion-pipeline-chunk-embed-chroma/`
- OpenSpec change: `openspec/changes/04-ingestion-pipeline-chunk-embed-chroma/`
- Define the `IngestionJob` model and owner linkage.
- Implement the Celery ingestion task: extract text (PDF/TXT/MD via LangChain loaders), chunk
  (`chunk_size = 1000`, `chunk_overlap = 150`), embed (local `all-MiniLM-L6-v2`), and upsert
  into the per-user Chroma collection `user_{user_id}`.
- Surface parse and embedding failures in both logs and task status.
- Implement `GET /api/documents/status/?task_id=<id>` returning public `PROCESSING`/`SUCCESS`/`FAILURE`
  with the internal-to-public status mapping; return `404` for unknown or non-owned tasks.

### 05. RAG Chat Query: OpenRouter

- Branch: `feature/05-rag-chat-query-openrouter`
- Feature workspace: `docs/02-features/05-rag-chat-query-openrouter/`
- OpenSpec change: `openspec/changes/05-rag-chat-query-openrouter/`
- Implement `POST /api/chat/query/` accepting `{ "query": ... }`.
- Retrieve owner-scoped context from the user's Chroma collection (`top_k = 4`, cosine).
- Assemble a bounded, context-grounded prompt and call the LLM via OpenRouter
  (`https://openrouter.ai/api/v1`, model `meta-llama/llama-3.3-70b-instruct:free`, verified at impl time).
- Apply the no-relevant-context guard.
- Return `{ "answer": ..., "tokens_consumed": ... }`, reading tokens from the response `usage`.
- Decrement the per-user credit balance by `tokens_consumed`.

### 07. Docker And Delivery: Compose, CI

- Branch: `feature/07-docker-and-delivery-compose-ci`
- Feature workspace: `docs/02-features/07-docker-and-delivery-compose-ci/`
- OpenSpec change: `openspec/changes/07-docker-and-delivery-compose-ci/`
- Write Dockerfiles and Docker Compose for web, PostgreSQL, Redis, Celery, Chroma, and the
  observability services (Grafana Alloy, Loki, Grafana).
- Configure structured JSON logging for Django and Celery; ship logs via Alloy to Loki;
  provision Grafana datasource and dashboard from version-controlled files.
- Add healthchecks and startup dependencies, `.env.example`, README run instructions, and API docs.

### 08. Bonus: Chat Continuation And SSE

- Branch: `feature/08-bonus-chat-continuation-sse`
- Feature workspace: `docs/02-features/08-bonus-chat-continuation-sse/`
- OpenSpec change: `openspec/changes/08-bonus-chat-continuation-sse/`
- Implement chat continuation by `chat_id` (owner-scoped; `404` for non-owned conversations).
- Implement Server-Sent Events (SSE) streaming for chat responses, preserving owner-scoping and
  the no-relevant-context guard.

## Suggested Delivery Order

1. foundation: branch and PR workflow (00)
2. foundation: Django + LangChain bootstrap (01)
3. authentication: register, login, JWT (02)
4. document upload (03)
5. ingestion pipeline and status (04)
6. RAG chat query (05)
7. Docker and delivery (07)
8. bonus: chat continuation and SSE (08)

## Acceptance Checklist

Mapped to the assessment's four parts.

### Part 1: Authentication & Subscription Management

- [ ] registration works (`POST /api/register/` -> `201` with `user_id`)
- [ ] login works (`POST /api/login/` -> `200` with JWT `token`)
- [ ] protected routes require a valid JWT; missing/invalid token -> `401`
- [ ] per-user credit balance exists and is decremented by tokens consumed

### Part 2: Document Management & Vector Storage (LangChain)

- [ ] upload accepts `.pdf`, `.txt`, `.md` and rejects others / oversize with `400`
- [ ] upload returns `202` with `document_id` and `task_id`
- [ ] ingestion runs asynchronously in Celery (extract -> chunk -> embed -> index)
- [ ] chunks are embedded with local `all-MiniLM-L6-v2` and stored in per-user Chroma collection
- [ ] ingestion status works (`PROCESSING`/`SUCCESS`/`FAILURE`); unknown/non-owned task -> `404`
- [ ] parse/embed failures surface in both logs and task status

### Part 3: RAG Chat Engine & Credit Consumption

- [ ] chat query works (`POST /api/chat/query/` -> `200` with `answer` and `tokens_consumed`)
- [ ] retrieval is owner-scoped (`top_k = 4`, cosine) to the user's collection only
- [ ] no-relevant-context guard answers "not enough information" instead of fabricating
- [ ] `tokens_consumed` is read from the LLM `usage` field, not estimated
- [ ] per-user credit balance decrements correctly

### Part 4: Dockerizing And Finalization

- [ ] Docker Compose runs web, database, Redis, Celery, Chroma, and dashboard services
- [ ] structured logs flow through Grafana Alloy into Loki and are visible in Grafana
- [ ] README includes setup and run instructions and the Docker commands
- [ ] API documentation is complete

### Bonus

- [ ] chat continuation by `chat_id` works and is owner-scoped
- [ ] SSE streaming works and preserves owner-scoping and the context guard
