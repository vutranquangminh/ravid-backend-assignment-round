# Proposal — s04 Ingestion pipeline (chunk → embed → Chroma) + status

> Workstream **04** · branch `feature/04-ingestion-pipeline-chunk-embed-chroma` · delivery artifacts in `docs/02-features/04-ingestion-pipeline/`. Completes RAVID brief **Part 2** (async ingestion + status).

## Why

Slice 03 stored uploads and enqueued a placeholder task. This slice makes ingestion real: extract text, chunk it, embed it, and index the vectors in a **per-user Chroma collection** — all asynchronously via Celery — and exposes `GET /api/documents/status/?task_id=` so clients can poll progress. This is the heart of the RAG knowledge base.

## What Changes

- **`IngestionJob` model** (`apps/rag/models.py`): `owner` FK, `source_document` FK, `status` (internal `PENDING`/`STARTED`/`SUCCESS`/`FAILURE`), `celery_task_id` (indexed, unique), `chunk_count`, `error_message`, `created_at`/`updated_at`. The DB row is the source of truth.
- **Real `ingest_document` task** (`apps/rag/tasks.py`): load (PyPDFLoader for PDF, text for TXT/MD) → `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)` → embed (local `all-MiniLM-L6-v2`) → upsert into Chroma collection `user_<owner_id>` with `document_id` metadata. Update the `IngestionJob` (`STARTED` → `SUCCESS` + `chunk_count`, or `FAILURE` + `error_message`). Failures are surfaced in BOTH structured logs and the job row.
- **Upload integration:** the upload flow now creates an `IngestionJob` and records its `celery_task_id`; `task_id` returned by upload maps to that job.
- **`GET /api/documents/status/?task_id=`** (JWT): look up the caller's `IngestionJob` by `celery_task_id`; map internal status to the brief's public `PROCESSING` / `SUCCESS` / `FAILURE` bodies. Unknown id or another user's id → `404`.
- **Embedding seam** for offline tests: a `get_embeddings()` factory overridable in `config.settings.test` with a deterministic stub (no model download, no network); Chroma runs against a temp persist dir.

## Capabilities

### New Capabilities
- `document-ingestion`: asynchronous text-extraction → chunk → embed → per-user Chroma indexing, with a polling status endpoint and per-user isolation of both jobs and vectors.

### Modified Capabilities
- (none — the upload endpoint's internal wiring changes but its external contract from s03 is unchanged.)

## Impact

- **New code:** `apps/rag/{models,pipeline,serializers,views,urls}.py` + migration; real `apps/rag/tasks.py`; `config/settings/base.py` (`CHROMA_PERSIST_DIR`, `EMBEDDING_MODEL`, splitter params), `config/settings/test.py` (stub embeddings, temp Chroma); tests.
- **Modified:** `apps/documents` upload flow (create `IngestionJob`); `config/urls.py` (status route); `tests/smoke/test_endpoints_absent.py` (remove `/api/documents/status/`; chat still absent).
- **Dependencies:** first use of the `rag` extra (chromadb, langchain, langchain-huggingface, sentence-transformers, pypdf).
- **Decisions:** per-user collection `user_<owner_id>`; internal-vs-public status mapping; embeddings stubbed in tests; deleting a Document also removes its vectors.
