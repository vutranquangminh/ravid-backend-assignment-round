# System Context

## Objective

Describe the major runtime components, their responsibilities, and how they
interact in the R.A.V.I.D. RAG document chatbot backend. This document freezes
the cross-cutting runtime topology before any feature slice is implemented.

Canonical locked decisions live in
`.agents/references/assessment-decisions.md`. Where this document references
values such as chunk size, top_k, the embedding model, or the LLM gateway, that
file is authoritative.

## Primary Actors

- User: registers, logs in, uploads private documents (`.pdf`, `.txt`, `.md`),
  waits for ingestion, then asks natural-language questions answered only from
  their own documents.
- Reviewer: runs the full Docker Compose stack locally, exercises the APIs,
  and inspects structured logs and the Grafana dashboard.

## Core Runtime Components

### Django API Service

Responsibilities:

- expose all public HTTP endpoints (health check, register, login, auth/me,
  document upload, document list, document delete, ingestion status, chat query,
  chat stream, OpenAPI schema, Swagger UI)
- validate requests (file type/size, payload shape)
- authenticate protected routes with JWT (`djangorestframework-simplejwt`)
- persist users, document metadata, and ingestion-job records
- enqueue background ingestion work onto Celery via Redis
- expose ingestion task status mapped to the public status vocabulary
- run the retrieval + LLM chain for chat queries and return the answer plus
  `tokens_consumed`
- decrement the per-user credit balance by the tokens the LLM reports

### PostgreSQL

Responsibilities:

- store relational application data as the system of record
- persist user accounts and per-user credit balance
- persist document metadata (owner, original name, storage path, content type,
  size, timestamps)
- persist ingestion-job records (status, celery task id, chunk count, error
  message, timestamps)
- persist optional conversation/message history for chat continuation

Postgres never stores file bytes or vector embeddings; those live on volumes.

### Redis

Responsibilities:

- broker Celery tasks (ingestion jobs)
- back Celery result state where the local workflow needs it

### Celery Worker

Responsibilities:

- execute the ingestion pipeline outside the request-response cycle
- load the uploaded file with the appropriate LangChain loader
- split text with `RecursiveCharacterTextSplitter`
- embed chunks with the local HuggingFace embedding model
- upsert vectors into the owner's Chroma collection (`user_{user_id}`)
- update the ingestion-job record (status, chunk_count, error_message)
- emit structured JSON logs with operation, document, task, and timing metadata

The worker must surface parse/embed failures in BOTH the structured logs and
the ingestion-job status (see `observability.md` and `database.md`).

### Local Embedding Model

Responsibilities:

- produce 384-dimension embeddings with HuggingFace `all-MiniLM-L6-v2` via
  `langchain-huggingface`
- run fully offline with no API key (the LLM gateway free tier has no
  embeddings endpoint)
- serve both the ingestion path (embed chunks) and the query path (embed the
  user question)

The model weights load inside the application/worker process; they are not a
separate network service.

### Chroma Vector Store

Responsibilities:

- persist per-user vector collections on a named volume
- expose one collection per user, named `user_{user_id}`, enforcing physical
  per-user isolation
- serve owner-scoped cosine similarity retrieval at `top_k=4`

Runs as its own container so it can persist independently of the web/worker
processes.

### OpenRouter LLM Provider

Responsibilities:

- act as the OpenAI-compatible LLM gateway at
  `https://openrouter.ai/api/v1` (chat/completions shape, NOT the Anthropic
  Messages shape)
- generate the final answer from the retrieved context and the user question
- report token usage in the response `usage` field; the application reads
  `tokens_consumed` from that field and never estimates it

This is the only external network dependency at request time. The model slug is
a free-tier slug recorded in the locked decisions; free slugs rotate and must be
verified at implementation time rather than answered from memory.

### File Storage Volume

Responsibilities:

- store original uploaded documents under `uploads/user_{user_id}/`
- back ingestion (the worker reads the original file from this volume)

Original files live on a named Docker volume, not in the database.

### Grafana Alloy

Responsibilities:

- collect logs from the Django and Celery containers
- forward logs to Loki

### Loki

Responsibilities:

- store and index the structured JSON logs

### Grafana

Responsibilities:

- provide dashboards and live log exploration split by service

## External Interfaces

### HTTP API

- liveness (`GET /api/health/`, public)
- registration (`POST /api/register/`)
- login (`POST /api/login/`)
- current user identity (`GET /api/auth/me/`, JWT)
- document upload (`POST /api/documents/upload/`, JWT)
- document list (`GET /api/documents/`, JWT, owner-scoped)
- document delete (`DELETE /api/documents/<id>/`, JWT, owner-scoped)
- ingestion status lookup (`GET /api/documents/status/?task_id=<id>`, JWT)
- chat query (`POST /api/chat/query/`, JWT)
- chat stream (`POST /api/chat/stream/`, JWT, SSE)
- OpenAPI schema (`GET /api/schema/`, public)
- Swagger UI (`GET /api/docs/`, public)

### JWT Authentication

- public endpoints (register, login) issue authentication state
- protected endpoints require `Authorization: Bearer <token>`
- missing or invalid JWT returns `401 Unauthorized`
- requests for a document, task, or vector collection outside the caller's
  ownership boundary return `404 Not Found` (never `403`, to avoid leaking
  existence)

## Main Interaction Flows

### Authentication Flow

1. User calls the registration or login endpoint.
2. Django validates credentials and account state.
3. Django returns the registration confirmation (`user_id`) or a JWT `token`.

### Upload And Ingestion Flow

1. User uploads a document to Django (multipart, field `file`).
2. Django validates type (`.pdf`/`.txt`/`.md` only) and size (max 10 MB),
   rejecting others with `400 {"error": "..."}`.
3. Django stores the original file under `uploads/user_{user_id}/`, creates the
   `Document` and `IngestionJob` rows, and dispatches a Celery task via Redis.
4. Django responds `202` with `document_id` and `task_id`.
5. The Celery worker loads -> splits (`RecursiveCharacterTextSplitter`,
   `chunk_size=1000`, `chunk_overlap=150`) -> embeds (local MiniLM) -> upserts
   into the owner's Chroma collection `user_{user_id}`.
6. The worker updates the ingestion job (`chunk_count`, terminal status) and, on
   failure, records `error_message` and surfaces it in logs.
7. User polls `GET /api/documents/status/?task_id=<id>` and receives
   `PROCESSING`, `SUCCESS`, or `FAILURE` (internal `STARTED` is mapped to public
   `PROCESSING`).

### Chat Query Flow (Owner-Scoped Retrieval)

1. Authenticated user calls `POST /api/chat/query/` with `{query}`.
2. Django embeds the query with the local MiniLM model.
3. Django retrieves the top 4 cosine-similar chunks scoped to the caller's
   collection (`user_{user_id}`) only.
4. If no relevant context is found, Django answers that there is not enough
   information in the user's documents (no fabrication).
5. Otherwise Django builds a bounded prompt from the retrieved chunks and calls
   OpenRouter (`chat/completions`).
6. Django reads `tokens_consumed` from the response `usage` field, decrements
   the user's credit balance, and returns `{answer, tokens_consumed}`.
7. Bonus: with a `chat_id`, prior turns are loaded for continuation; SSE streams
   the answer incrementally.

### Observability Flow

1. Django and Celery emit structured JSON logs to stdout.
2. Docker captures container stdout.
3. Alloy scrapes container logs and forwards them to Loki.
4. Grafana queries Loki and renders dashboards and live log streams.

## Context Boundaries

### Inside The Application Boundary

- Django API service
- Celery worker
- local embedding model (in-process)
- PostgreSQL data
- application-managed file storage volume
- Chroma vector store

### Supporting Platform Components

- Redis
- Alloy
- Loki
- Grafana
- Docker Compose

### External Dependency

- OpenRouter LLM gateway (only request-time external call)

## Design Principles

- keep the runtime topology minimal and reviewer-friendly
- keep background processing explicit and observable
- enforce per-user isolation physically (one collection per user) and in authz
  (404-not-403 leak rule)
- treat the database row as the source of truth for status, never the broker
- never log secrets or raw document text
- read provider token usage from the response, never estimate; verify rotating
  provider/model details at implementation time rather than from memory
