# Observability Design

## Objective

Define the logging, collection, storage, and dashboard strategy for the
R.A.V.I.D. backend so that ingestion and chat behavior is visible to a reviewer
without reading code, and so that failures are traceable.

## Logging Format

All application and worker logs are emitted as structured JSON to stdout.

### JSON Log Field Contract

The following fields form the log payload contract. Fields are included when
relevant to the operation; ids stay in the payload, never as Loki labels.

- `ts` — ISO-8601 timestamp
- `level` — log level (`INFO`, `WARNING`, `ERROR`, ...)
- `logger` — logger name / service origin
- `request_id` — correlation id for an HTTP request (when available)
- `user_id` — authenticated user id (when available and safe)
- `document_id` — relevant document id (upload/ingest paths)
- `task_id` — Celery task id (ingestion paths)
- `chat_id` — conversation id (chat-continuation paths)
- `collection` — the per-user Chroma collection name `user_{user_id}`
- `operation` — one of `upload`, `embed`, `retrieve`, `llm`
- `num_chunks` — number of chunks produced/stored (ingest) or retrieved (query)
- `retrieval_k` — the top_k used for retrieval (4)
- `llm_model` — the OpenRouter model slug used for the call
- `prompt_tokens` — prompt tokens from the provider `usage` field
- `completion_tokens` — completion tokens from the provider `usage` field
- `duration_ms` — operation duration in milliseconds

### Operation Tagging

The `operation` field is the primary way to slice RAG behavior:

- `upload` — request received, file validated and stored, job dispatched
- `embed` — chunking + embedding + Chroma upsert (worker)
- `retrieve` — owner-scoped similarity search for a query
- `llm` — the OpenRouter chat/completions call and its token usage

## Hard Rules (Never Log)

- never log the `OPENROUTER_API_KEY`, the JWT, or any credential
- never log raw document text or raw chunk content
- never log the embedding vectors
- never log the full user query content as a label (it may go in the payload at
  INFO only if needed, but prefer metadata over content)

A leak of secrets or document text into logs is a defect (see MISTAKE M-008).

## Service Tagging Strategy

Use explicit, low-cardinality service labels so logs split cleanly in Loki and
Grafana:

- `service=django`
- `service=celery`

## Collection Strategy

- Django and Celery write JSON logs to stdout.
- Docker captures container stdout.
- Grafana Alloy scrapes container logs from the Docker environment.
- Alloy forwards the logs to Loki.

## Loki Label Strategy

Keep labels minimal and low-cardinality to avoid cardinality explosion.

Recommended labels:

- `service` (django | celery)

Keep all high-cardinality identifiers (`request_id`, `user_id`, `document_id`,
`task_id`, `chat_id`, `collection`) in the JSON payload, never as labels.

## Grafana Dashboard Requirements

### Required Panel

- live stream of logs filtered by service (Django and Celery)

### Bonus Panel 1

- count of error-level logs over the last 30 minutes

### Bonus Panel 2

- token consumption and/or slowest operations by `duration_ms`, sliced by
  `operation` (`embed`, `retrieve`, `llm`)

## Failure Visibility Rules

- application exceptions appear in the JSON logs with context
- ingestion failures (parse/embed/store) must include `task_id`, `document_id`,
  `operation`, and the error context
- an ingestion failure must be visible BOTH in the logs AND through the
  ingestion-status API (`status=FAILURE` with `error`). Surfacing it in only
  one place is a defect (MISTAKE M-006).
- retrieval that returns no relevant context is logged at INFO with `operation`
  = `retrieve` and `num_chunks` = 0, and the chat answer states there is not
  enough information in the user's documents.

## Log Retention Assumption

- the local assessment stack uses simple local retention only
- no long-term retention guarantees are required for submission

## Reviewer Experience Goal

The reviewer should be able to:

- start the stack
- open Grafana
- distinguish Django and Celery logs immediately by `service`
- follow a single ingestion or chat flow end to end via `task_id` / `request_id`
  in the payload
- confirm token consumption and operation timing without reading code first
