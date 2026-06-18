# AI Programming Guidelines (RAVID)

You are building a RAG document-chatbot backend (RAVID) as a time-boxed assessment.
Optimize for clean delivery, clear contracts, per-user data isolation, and minimal rework.

These are **always-on gates**: they apply to every slice unless a slice's OpenSpec
`design.md` explicitly and visibly overrides one with a stated reason.

## Core Principles

- Favor simple, explicit designs over general-purpose abstractions.
- Use Django and DRF conventions unless there is a clear reason not to.
- Keep code easy to review under time pressure.
- Make behavior visible in docs, tests, structured logs, and task status.
- Per-user isolation is a correctness property, not an enhancement: every document,
  ingestion task, and vector lookup is scoped to the authenticated owner by default.

## Stack Conventions (locked)

Canonical values live in `.agents/references/assessment-decisions.md`. Do not restate
or fork them here; reference that file. In short:

- Django 5.x handles project structure, settings, auth integration, and ORM.
- DRF handles serializers, request parsing, permissions, and API responses.
- `djangorestframework-simplejwt` handles JWT-based auth.
- Celery handles long-running ingestion (load -> split -> embed -> upsert).
- Redis is the broker and result backend unless the project explicitly changes it.
- PostgreSQL is the default relational database (source-of-truth metadata).
- Chroma is the vector store; **one collection per user** named `user_{user_id}`.
- LangChain provides loaders, `RecursiveCharacterTextSplitter`, and the retriever.
- OpenRouter is the LLM gateway (OpenAI-compatible). See
  `.agents/guidelines/llm-provider-guidelines.md`. Never answer provider/model
  details from memory.
- Embeddings are **local HuggingFace** (`all-MiniLM-L6-v2`, 384 dims) via
  `langchain-huggingface`. No embedding API key, no network call to embed.

## API Design

- Keep request and response contracts stable and documented; match the assessment
  endpoints **exactly** (see `.agents/references/assessment-decisions.md`).
- Use serializers for validation, not ad-hoc parsing in views.
- Keep views thin; service or task orchestration must be explicit and testable.
- Return the single-field error envelope `{"error": "<message>"}` everywhere, with
  actionable messages. Do not invent alternate error shapes.
- Do not silently accept malformed payloads just to be permissive.
- Upload contract: accept `.pdf .txt .md` only, max 10 MB; reject anything else with
  HTTP 400 `{"error": "..."}` **before** queuing any Celery work.

## Ownership And Isolation (non-negotiable)

- Every model that holds user data carries an owner FK; every queryset is filtered to
  `request.user` first, then by id.
- Cross-user access to a document, task, or vector returns **HTTP 404**, never 403, so
  existence is not leaked.
- Missing or invalid JWT returns **HTTP 401**.
- Vector retrieval is always scoped to the caller's `user_{user_id}` collection. Never
  query, merge, or fall back to another user's collection.

## File And Storage Boundaries

- Keep the uploaded source file, derived chunks, and vector data on clearly separate
  boundaries: original file in file storage, chunk/vector data in Chroma, authoritative
  metadata and status in Postgres.
- Never store raw document text in logs. Persist enough metadata (document id, owner,
  task id, status, failure reason, chunk count, collection name) to reconstruct state.
- The DB row is the source of truth for status and ownership; the vector store and task
  backend are derived state.

## Celery And Async Work

- Offload load -> `RecursiveCharacterTextSplitter` (chunk_size=1000, overlap=150) ->
  embed -> Chroma upsert to Celery. The upload view returns `202` with `task_id`.
- Validate uploads (type, size, presence) **before** queuing the task.
- Make task states and failure reasons observable through the status endpoint and logs.
- Map internal Celery states to the public contract: `PROCESSING | SUCCESS | FAILURE`.
- Do not swallow parse/embedding exceptions. Capture them, mark the task `FAILURE`, and
  surface the reason in **both** the status response and structured logs (M-006).

## RAG Query Path

- Retrieve top_k=4 by cosine similarity from the caller's collection only.
- Bound the context sent to the LLM: pass only the retrieved chunks, never the full
  corpus or unbounded history (M-007).
- If retrieval returns nothing relevant, answer that there is not enough information in
  the user's documents. Do not let the LLM hallucinate from general knowledge.
- Read `tokens_consumed` from the provider response `usage` field; never estimate.
- Decrement the per-user credit balance by the actual `tokens_consumed`.

## Observability

- Emit structured JSON logs from Django and Celery (Alloy -> Loki -> Grafana).
- Include stable fields when relevant:
  - `service`
  - `environment`
  - `user_id`
  - `task_id`
  - `task_name`
  - `document_id`
  - `collection`
  - `operation`
  - `status`
  - `tokens_consumed`
  - `duration_ms`
- **Never** log secrets, full tokens, API keys, embeddings, or raw document/chunk text
  (M-008). Log counts and ids, not content.
- Prefer log fields over string-only messages for machine analysis.

## Validation And Testing

- Write tests close to the behavior being added.
- Cover: happy path, upload validation errors (type/size), auth failures (401),
  cross-user isolation (404), async state transitions (PROCESSING/SUCCESS/FAILURE),
  no-relevant-context guard, and the integration seams.
- Use deterministic PDF/TXT/MD fixtures; do not depend on live network for embeddings.
- Add smoke coverage for Docker and observability where practical.
- Record validation commands and outcomes in the slice's `validation-report.md`.

## Error Handling

- Validate all external input explicitly.
- Fail with clear `{"error": ...}` messages for unsupported file types, oversized or
  missing files, invalid queries, and bad auth.
- Embedding/parse failures must surface in both task status and logs, never be silently
  dropped (M-006).

## Review Expectations

- Reviews focus on bugs, regressions, missing tests, weak contracts, isolation/secret
  leaks, provider/model verification, and repeated mistakes.
- Reviewers must cross-check active mistake rules in `.agents/MISTAKE.md`.
- If a new recurring issue class is found, add it to the ledger immediately.
