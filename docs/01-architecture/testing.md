# Testing Strategy

## Objective

Define a practical testing approach for the R.A.V.I.D. RAG backend that balances
confidence with delivery speed, with explicit priority on per-user isolation,
ingestion failure propagation, and owner-scoped retrieval.

## Offline Test Posture

Tests run fully offline and deterministically. In `config/settings/test.py`:

- `CELERY_TASK_ALWAYS_EAGER = True` so ingestion runs synchronously in-process
- the embedding model is stubbed (deterministic vectors), so tests do not
  download or run MiniLM weights
- the OpenRouter client is stubbed, returning a canned answer and a fixed
  `usage` block so `tokens_consumed` is assertable without a network call
- Chroma uses a temporary/isolated location so collections do not leak between
  tests

No test may make a real network call to OpenRouter or download model weights.

## Testing Layers

### Unit Tests

Focus on:

- serializer validation (register, login, upload, chat query)
- file validation helpers (type allowlist, 10 MB size limit)
- the internal-to-public status mapping (`PENDING`/`STARTED` -> `PROCESSING`)
- the chunking step shape (`chunk_size=1000`, `chunk_overlap=150`)
- the no-relevant-context guard
- the credit decrement helper (decrements by `tokens_consumed`)
- model helper methods

### API Integration Tests

Focus on:

- registration (success, duplicate email -> 400)
- login (success returns `token`, invalid credentials -> 401)
- protected route enforcement (missing/invalid JWT -> 401)
- document upload (accepted -> 202 with `document_id` + `task_id`)
- ingestion status responses (PROCESSING / SUCCESS / FAILURE)
- chat query (answer + `tokens_consumed`)

### Async / Pipeline Integration Tests

Focus on:

- end-to-end ingestion via eager Celery: load -> split -> embed (stub) ->
  Chroma upsert, with `chunk_count` recorded on the job
- ingestion failure propagation (parse/embed error sets `status=FAILURE`,
  populates `error_message`, and emits an error log)
- owner-scoped retrieval correctness (a query only ever reads the caller's
  collection)

### Smoke Tests

Focus on:

- Docker Compose boot path and service readiness
- observability pipeline availability (Grafana can query Loki after startup)

## Priority Scenarios

### Authentication

- successful registration -> 201 with `user_id`
- duplicate / invalid registration -> 400 `{error}`
- successful login -> 200 with `token`
- invalid credential rejection -> 401 `{error}`
- unauthorized access to any protected route -> 401 `{error}`

### Upload (Type / Size Rejection)

- valid `.pdf`, `.txt`, `.md` upload -> 202
- unsupported type (e.g. `.csv`, `.docx`, `.exe`) -> 400 `{error}`
- file larger than 10 MB -> 400 `{error}`
- missing file field -> 400 `{error}`

### Cross-User Isolation (404, not 403)

- requesting another user's ingestion `task_id` -> 404 `{error}`
- requesting another user's `document_id` (list/delete) -> 404 `{error}`
- a chat query by user A never retrieves user B's chunks (assert retrieval is
  scoped to `user_{A}` collection only)

### Ingestion Failure Propagation

- a deliberately unparsable / corrupt fixture sets `status=FAILURE` with a
  populated `error_message`
- the same failure appears in the structured logs (`operation` context)
- the failure is observable through `GET /api/documents/status/`

### Retrieval Correctness (Owner-Scoped)

- after ingesting a known fixture, a query whose answer is in the fixture
  retrieves the relevant chunk(s) from the owner's collection
- `retrieval_k` is 4 and similarity is cosine
- a query with no relevant content returns the "not enough information"
  answer and does not fabricate

### Chat Answer + Tokens

- a successful query returns `{answer, tokens_consumed}`
- `tokens_consumed` equals the value from the stubbed provider `usage` field
  (never an estimate)
- the user's credit balance is decremented by `tokens_consumed`
- insufficient credit -> 402 `{error}` (if credit enforcement is enabled)

### Observability

- Django emits JSON logs with the documented field contract
- Celery emits JSON logs with `task_id`, `operation`, and timing
- secrets and raw document text never appear in logs
- Grafana can query Loki after stack startup; required live log panel and
  documented bonus panels exist if implemented

## Test Data Strategy

Fixtures are generated programmatically inside the tests rather than stored as
version-controlled files. Each test that needs document content creates it in-memory:

- a deterministic small in-memory `.txt` payload with known sentences for predictable retrieval
- a deterministic small in-memory `.md` payload with headings and known facts
- a minimal valid PDF built in-memory with known text
- a deliberately corrupt / unparsable byte payload to drive failure propagation

There is no `tests/fixtures/` directory. Fixtures are kept small so embedding
(even stubbed) and chunking are fast and predictable.

## Delivery Rule

- prioritize tests for public API behavior, per-user isolation, and async
  ingestion state transitions first
- add smoke coverage for Docker and observability before submission
- record executed validation commands and outcomes in the per-feature
  `docs/02-features/<NN-name>/validation-report.md`
