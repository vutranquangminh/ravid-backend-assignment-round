# Database Design

## Objective

Define the minimum relational model needed to support authentication and a
per-user credit balance, document uploads, asynchronous ingestion, ingestion
status reporting, and optional chat continuation.

PostgreSQL is the system of record for status and metadata. File bytes and
vector embeddings are NOT stored in the database; they live on volumes (the file
storage volume and the Chroma volume respectively).

## Primary Models

### User

Use Django's built-in user model as the authentication base.

Core needs:

- unique identity
- email-based login (`email` + `password` per the assessment payloads)
- password management through Django auth

### Credit / Balance

Per-user credit balance, decremented by `tokens_consumed` after each chat query
(the brief implies this under Subscription Management / Credit Consumption).

Two acceptable shapes:

- a `credit_balance` integer field on a `Profile`/extended user model, or
- a small `CreditAccount(owner OneToOne, balance, updated_at)` model

Whichever is chosen, decrement happens in the chat service after the LLM call,
using the `tokens_consumed` value read from the provider `usage` field. Never
estimate the decrement.

### Document

Purpose:

- represent an uploaded source document owned by a user

Suggested fields:

- `id`
- `owner` (FK to User, indexed)
- `original_name`
- `storage_path` (e.g. `uploads/user_{user_id}/<file>`)
- `content_type`
- `size_bytes`
- `uploaded_at`

Responsibilities:

- map the public `document_id` to persisted document metadata
- support ownership checks for protected access (cross-user access -> 404)

### IngestionJob

Purpose:

- represent an ingestion request tied to an uploaded document

Suggested fields:

- `id`
- `owner` (FK to User)
- `source_document` (FK to Document)
- `celery_task_id` (indexed)
- `status`
- `chunk_count`
- `error_message`
- `created_at`
- `updated_at`
- `completed_at`

Responsibilities:

- track queued, running, and finished ingestion runs
- back the ingestion status API lookup by `task_id`
- persist enough state to surface failures (`error_message`, `status`) and
  success detail (`chunk_count`)

### Conversation / Message (Optional, Bonus)

Purpose:

- support chat continuation via `chat_id`

Suggested shape:

- `Conversation(id, owner FK, created_at)` — `id` is the public `chat_id`
- `Message(id, conversation FK, role, content, tokens_consumed, created_at)`

Used only by the chat-continuation bonus; the core chat query works without it.

## Relationship Model

- one user owns many documents
- one user owns many ingestion jobs
- one document has one (or, if re-ingestion is supported, many) ingestion jobs
- one ingestion job has exactly one source document
- one user owns many conversations; one conversation has many messages

## Status Model

Internal application status values on `IngestionJob`:

- `PENDING`
- `STARTED`
- `SUCCESS`
- `FAILURE`

The public ingestion-status API uses the assessment vocabulary:

- `PROCESSING`
- `SUCCESS`
- `FAILURE`

Mapping rule:

- internal `PENDING` and `STARTED` are both exposed as public `PROCESSING`
- `SUCCESS` and `FAILURE` pass through unchanged

The database row is the source of truth for status. Do not derive public status
from the Celery result backend; read it from the `IngestionJob` row.

## Persistence Decisions

- original uploaded files are stored on the file storage volume under
  `uploads/user_{user_id}/`, not in database blobs
- vector embeddings are stored in Chroma (one collection per user,
  `user_{user_id}`) on the Chroma volume, not in the database
- ingestion outcome metadata (`chunk_count`, `error_message`, `status`,
  timestamps) lives on the `IngestionJob` row

## Failure Surfacing Rule

When ingestion fails (parse error, embedding error, store error), the worker
must set `status=FAILURE` and populate `error_message`, AND emit a structured
log with the failure context. A swallowed failure that does not appear in both
the status row and the logs is a defect (see MISTAKE M-006).

## Per-User Isolation Rule

Every document, ingestion job, and vector collection is owned. Cross-user reads
return `404` (never `403`). Retrieval queries are scoped to the caller's
collection only; a query must never read another user's vectors (MISTAKE M-005).

## Indexing Guidance

Index the following:

- `IngestionJob.celery_task_id` (status lookup by `task_id`)
- `IngestionJob.status`
- `IngestionJob.source_document_id`
- `IngestionJob.owner_id`
- `Document.owner_id`

## Non-Goals

- no advanced audit-trail tables in v1
- no multi-tenant partitioning beyond per-user collections
- no event-sourcing model
- no storage of file bytes or embedding vectors in the relational database
