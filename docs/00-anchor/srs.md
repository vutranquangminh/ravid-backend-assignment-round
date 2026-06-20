# Software Requirements Specification

## Purpose

This document translates the assessment brief into a stable technical requirements baseline
for implementation. Functional requirements use "shall" statements. Each requirement maps to
the actual endpoints named in the assessment PDF and to the locked decisions recorded in
`.agents/references/assessment-decisions.md`.

## System Overview

The system is a Django-based backend for a Retrieval-Augmented Generation (RAG) document
chatbot. It supports:

- user registration and login with JWT issuance
- JWT-protected document and chat routes
- authenticated private document upload (PDF, TXT, Markdown)
- asynchronous ingestion (text extraction, chunking, embedding, per-user vector indexing)
- ingestion task status retrieval
- owner-scoped retrieval and LLM-backed chat answers via OpenRouter
- per-user credit consumption tracking
- centralized structured logging
- Dockerized local execution

## Functional Requirements

### FR-1 User Registration

- The system shall expose `POST /api/register/`.
- The endpoint shall accept a JSON body with `email` and `password` (multipart form-data is
  also acceptable per the brief).
- The endpoint shall create a user account when the request is valid.
- On success the endpoint shall return `201 Created` with `{ "message": "...", "user_id": "<user_id>" }`.
- On failure (for example, an email that already exists) the endpoint shall return
  `400 Bad Request` with the error envelope `{ "error": "<message>" }`.

### FR-2 User Login

- The system shall expose `POST /api/login/`.
- The endpoint shall accept a JSON body with `email` and `password`.
- The endpoint shall authenticate the user.
- On success the endpoint shall return `200 OK` with `{ "message": "...", "token": "<jwt_access_token>" }`.
- On failure the endpoint shall return `401 Unauthorized` with `{ "error": "Invalid email or password" }`.

### FR-3 Route Protection

- The system shall require a valid JWT access token, passed as `Authorization: Bearer <token>`,
  for all protected routes.
- Registration and login shall remain public.
- Document upload, ingestion status, and chat query endpoints shall be protected.
- A missing or invalid JWT on a protected route shall return `401 Unauthorized` with the error envelope.

### FR-4 Document Upload

- The system shall expose `POST /api/documents/upload/`.
- The endpoint shall accept `multipart/form-data` with a `file` field.
- The endpoint shall accept only `.pdf`, `.txt`, and `.md` files.
- The endpoint shall reject other file types with `400 Bad Request` and the error envelope,
  for example `{ "error": "Invalid file format. Only PDF, TXT, and Markdown files are allowed." }`.
- The endpoint shall reject files larger than 10 MB with `400 Bad Request` and the error envelope.
- The endpoint shall persist the uploaded file and a document record owned by the authenticated user.
- The endpoint shall enqueue an asynchronous ingestion task and return `202 Accepted` with
  `{ "message": "...", "document_id": "<document_id>", "task_id": "<task_id>" }`.

### FR-5 Ingestion Task Status

- The system shall expose `GET /api/documents/status/`.
- The request shall accept the query parameter `task_id`.
- The endpoint shall return `{ "task_id": "<id>", "status": "PROCESSING" }` while the task runs.
- On success the endpoint shall return `status: "SUCCESS"` with a confirmation message, for example
  "Document successfully parsed, embedded, and indexed in vector storage."
- On failure the endpoint shall return `status: "FAILURE"` with the error envelope describing
  the failure, for example `{ "error": "Failed to parse document content." }`.
- The public status values shall be exactly `PROCESSING`, `SUCCESS`, and `FAILURE`.
- Internal Celery states shall map to public values: `PENDING`/`STARTED`/`RETRY` map to
  `PROCESSING`; `SUCCESS` maps to `SUCCESS`; `FAILURE`/`REVOKED` map to `FAILURE`.
- The endpoint shall return `404 Not Found` when the task does not exist or does not belong
  to the authenticated user.

### FR-6 Text Extraction

- The ingestion pipeline shall extract raw text content from the uploaded file according to type.
- The pipeline shall support PDF, TXT, and Markdown extraction using LangChain document loaders.
- An extraction failure shall be surfaced in both the structured logs and the task status as
  a `FAILURE`; it shall not be silently swallowed.

### FR-7 Chunking

- The pipeline shall split extracted text into contextual chunks using LangChain's
  `RecursiveCharacterTextSplitter`.
- The chunker shall use `chunk_size = 1000` and `chunk_overlap = 150`.

### FR-8 Embedding

- The pipeline shall compute vector embeddings for each chunk using a local, free,
  open-source embedding model (HuggingFace `all-MiniLM-L6-v2`, 384 dimensions) via
  `langchain-huggingface`.
- The pipeline shall not depend on a paid embedding provider, and shall not require an
  embedding API key, because the OpenRouter free tier offers no embedding models.
- An embedding failure shall be surfaced in both the structured logs and the task status as
  a `FAILURE`.

### FR-9 Per-User Vector Storage

- The pipeline shall store chunk vectors in Chroma.
- The system shall maintain one Chroma collection per user, named `user_{user_id}`.
- Each stored chunk shall carry metadata sufficient to attribute it to its source document
  and owning user.
- The system shall never write one user's chunks into another user's collection.

### FR-10 Owner-Scoped Retrieval

- The chat pipeline shall retrieve context using a LangChain vector store retriever scoped to
  the authenticated user's collection only.
- The retriever shall use cosine similarity and `top_k = 4`.
- The retrieval scope shall be derived from the authenticated user identity, never from a
  client-supplied identifier.

### FR-11 RAG Chat Query

- The system shall expose `POST /api/chat/query/`.
- The endpoint shall accept a JSON body with `query`.
- The endpoint shall retrieve owner-scoped context (FR-10), assemble a context-grounded prompt,
  and obtain an answer from the LLM via OpenRouter.
- On success the endpoint shall return `200 OK` with `{ "answer": "<text>", "tokens_consumed": <int> }`.
- The endpoint shall read `tokens_consumed` from the LLM response `usage` field and shall not
  estimate it.

### FR-12 No-Relevant-Context Guard

- When owner-scoped retrieval returns no relevant context for a query, the system shall return
  an answer stating that there is not enough information in the user's documents to answer.
- The system shall not fabricate an answer from model parametric knowledge when no relevant
  context is found.

### FR-13 Credit Consumption

- The system shall maintain a simple per-user credit balance.
- After each successful chat answer, the system shall decrement the user's credit balance by
  the `tokens_consumed` value reported by the LLM response.
- The credit balance shall be persisted per user in the database.

### FR-14 LLM Gateway Integration

- The system shall route LLM requests through OpenRouter at base URL
  `https://openrouter.ai/api/v1`, using the OpenAI-compatible chat/completions request shape.
- The system shall use a free-tier model slug (target `google/gemma-4-31b-it:free`),
  recognizing that free slugs rotate and shall be verified at implementation time.
- The OpenRouter API key shall be read from configuration and shall never be logged.

### FR-15 Persistence And Ownership

- The system shall persist document metadata, ingestion job state, and chat records in the database.
- Every document, ingestion job, vector collection, and chat record shall be linked to an owning
  user via a foreign key.
- The database row shall be the source of truth for ownership and task lifecycle state.

### FR-16 Structured Observability

- Django logs shall be emitted in JSON format.
- Celery logs shall be emitted in JSON format.
- Celery logs shall include task metadata such as `task_id` and `task_name`.
- Logs shall be collected by Grafana Alloy and shipped to Loki.
- Grafana shall expose a dashboard for log inspection.
- The system shall never log secrets (JWT, OpenRouter key, embedding configuration) or raw
  document text.

### FR-17 Dashboard Visibility

- The dashboard shall show live logs by service (`service=django`, `service=celery`).
- The solution should support useful operational panels, for example error-level log count
  over the last 30 minutes and the slowest ingestion or chat operations by logged `duration_ms`.

### FR-18 Dockerized Delivery

- The project shall run via Docker and Docker Compose.
- The stack shall include: web application, PostgreSQL, Redis, Celery worker, Chroma vector
  store, and the observability services (Alloy, Loki, Grafana).
- The README shall provide the commands required to run the stack.

### FR-19 API Documentation

- The solution shall include API documentation.
- The documentation tool may be OpenAPI, Bruno, Postman, or another widely used option.

### FR-20 Chat Continuation (Bonus)

- The system should expose a way to continue an existing conversation by providing a `chat_id`
  (or prior message history) so that follow-up questions retain conversational context.
- Continuation shall remain owner-scoped: a user may only continue their own conversations,
  and a `chat_id` not owned by the requester shall return `404 Not Found`.

### FR-21 SSE Streaming (Bonus)

- The system should support streaming chat responses in real time using Server-Sent Events (SSE).
- Streaming shall preserve the same owner-scoping and no-relevant-context guard as the
  non-streaming path.

## Non-Functional Requirements

### NFR-1 Maintainability

- The solution should favor simple, explicit design over unnecessary abstraction.
- Contracts and assumptions should be documented.

### NFR-2 Reviewability

- The solution should be easy for reviewers to run and inspect locally.
- The README should make the evaluation path obvious.

### NFR-3 Reliability

- Invalid inputs should fail clearly with the error envelope.
- Ingestion failures (parse, embed, index) shall be visible through both logs and task status.

### NFR-4 Security And Per-User Isolation

- Protected routes shall enforce JWT authentication; missing or invalid JWT returns `401 Unauthorized`.
- Each user's documents, chunks, vectors, and chat history shall be isolated; a user shall not be
  able to read or query another user's data.
- Cross-user access to a document, task, vector collection, or chat shall return `404 Not Found`
  rather than `403`, to avoid leaking resource existence.
- Secrets (JWT, OpenRouter key) and raw document text shall not be logged.

### NFR-5 Asynchronous Processing

- Document ingestion shall run in Celery workers, not in the request-response cycle.
- The upload endpoint shall return promptly with `202 Accepted` and a `task_id` for polling.

### NFR-6 Observability

- The system should provide enough structured metadata to trace ingestion and chat behavior,
  including correlation by `task_id`, `document_id`, and user where appropriate (kept in JSON
  payload, not as high-cardinality log labels).

### NFR-7 Cost

- The full pipeline shall run free of charge: OpenRouter free-tier LLM and local open-source
  embeddings, with no paid API keys required.

## Technical Baseline

The following stack is locked. Version families are pinned at implementation time; the exact
pins live in `.agents/references/assessment-decisions.md` and the dependency manifest.

- Python `3.12`
- Django `5.x`
- Django REST Framework
- `djangorestframework-simplejwt`
- Celery `5.x`
- Redis (broker and result backend)
- PostgreSQL
- Chroma (vector store)
- LangChain (document loaders, `RecursiveCharacterTextSplitter`, vector store retriever)
- `langchain-huggingface` with local embedding model `all-MiniLM-L6-v2` (384 dims)
- OpenRouter as the LLM gateway (`https://openrouter.ai/api/v1`, OpenAI-compatible),
  target model `google/gemma-4-31b-it:free`
- Grafana Alloy + Loki + Grafana for observability
- Docker Compose for delivery

### Locked RAG Parameters

- Chunking: `RecursiveCharacterTextSplitter`, `chunk_size = 1000`, `chunk_overlap = 150`
- Retrieval: `top_k = 4`, cosine similarity
- Vector isolation: one Chroma collection per user, named `user_{user_id}`
- Uploads: `.pdf`, `.txt`, `.md` only; maximum 10 MB
- Token accounting: read from LLM response `usage`; never estimate
- Error envelope: `{ "error": "<message>" }` everywhere

## Known Ambiguities And Current Defaults

Each default below is cross-linked to `.agents/references/assessment-decisions.md`, which is the
canonical source of locked decisions. If any default changes, update the decisions file first.

### Vector Store Choice

- Ambiguity: the brief allows Chroma, FAISS, or Pinecone.
- Default: use Chroma, one collection per user named `user_{user_id}`, for free local per-user isolation.

### Embedding Provider

- Ambiguity: the brief allows any open-source or commercial embedding model; OpenRouter's free
  tier offers no embeddings.
- Default: local HuggingFace `all-MiniLM-L6-v2` (384 dims) via `langchain-huggingface` (free, offline).

### LLM Model Slug

- Ambiguity: the brief lists several free models (Mistral 7B, Gemma, OpenChat variants) and free
  slugs rotate.
- Default: target `google/gemma-4-31b-it:free`, verified at implementation time;
  never answered from memory.

### Chunking Parameters

- Ambiguity: the brief names `RecursiveCharacterTextSplitter` but does not fix sizes.
- Default: `chunk_size = 1000`, `chunk_overlap = 150`.

### Retrieval Parameters

- Ambiguity: the brief does not fix `top_k` or the similarity metric.
- Default: `top_k = 4`, cosine similarity.

### Upload Constraints

- Ambiguity: the brief lists allowed types but not a size limit.
- Default: allow `.pdf`, `.txt`, `.md` only, maximum 10 MB; reject others with `400` and the error envelope.

### Ingestion Status Mapping

- Ambiguity: the brief shows public states `PROCESSING`, `SUCCESS`, `FAILURE` but Celery uses
  finer internal states.
- Default: map `PENDING`/`STARTED`/`RETRY` to `PROCESSING`; `SUCCESS` to `SUCCESS`;
  `FAILURE`/`REVOKED` to `FAILURE`.

### Unknown Or Cross-User Task Handling

- Ambiguity: the brief does not define responses for unknown or non-owned task ids.
- Default: return `404 Not Found`.

### Ownership Policy

- Ambiguity: the brief does not define cross-user access behavior for documents, tasks,
  vectors, or chats.
- Default: enforce ownership via owner foreign keys and return `404 Not Found` for resources
  not owned by the requester.

### No-Relevant-Context Behavior

- Ambiguity: the brief does not define what to answer when retrieval finds nothing relevant.
- Default: answer that there is not enough information in the user's documents; do not fabricate.

### Credit Balance Model

- Ambiguity: the brief mentions credit consumption and tokens consumed but does not define a
  credit model.
- Default: maintain a simple per-user credit balance decremented by `tokens_consumed` per answer.

### Token Counting

- Ambiguity: the brief shows `tokens_consumed` in the response but not its source.
- Default: read it from the LLM response `usage` field; never estimate.
