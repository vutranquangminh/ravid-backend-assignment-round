# Proposal — s03 Document upload (PDF / TXT / MD)

> Workstream **03** · branch `feature/03-document-upload-pdf-txt-md` · delivery artifacts in `docs/02-features/03-document-upload/`. Implements the upload half of RAVID brief **Part 2**.

## Why

Users build a private knowledge base by uploading documents. This slice delivers the authenticated upload endpoint, the `Document` model that anchors per-user ownership, and the validation + storage rules — plus the async hand-off contract (`202` + `task_id`). The actual ingestion pipeline (parse → chunk → embed → Chroma) is slice 04; here we define and enqueue it.

## What Changes

- **`Document` model** (`apps/documents`): `owner` FK (indexed), `original_name`, `file` (stored under `uploads/user_<id>/`), `content_type`, `size_bytes`, `status` (UPLOADED), `uploaded_at`.
- **`POST /api/documents/upload/`** (JWT, multipart `file`): validate type (`.pdf/.txt/.md` by extension AND content-type) and size (≤ 10 MB), save the file, create the `Document`, enqueue ingestion, return `202 {message, document_id, task_id}`. Bad type → `400 {"error":"Invalid file format. Only PDF, TXT, and Markdown files are allowed."}`.
- **`GET /api/documents/`** (JWT): list the caller's own documents only.
- **`DELETE /api/documents/<id>/`** (JWT): delete a caller-owned document (and its file); another user's id → `404` (never 403 — no existence leak).
- **Ingestion task seam** (`apps/rag/tasks.py`): `ingest_document(document_id)` Celery task — a placeholder in this slice (logs + marks the doc), fully implemented in slice 04. Upload enqueues it and returns its task id.

## Capabilities

### New Capabilities
- `document-management`: authenticated upload with type/size validation, per-user document storage and ownership, list/delete with cross-user 404 isolation, and the async ingestion hand-off (`202` + `task_id`).

### Modified Capabilities
- (none)

## Impact

- **New code:** `apps/documents/{models,serializers,services,views,urls,apps}.py` + migration; `apps/rag/tasks.py` (ingestion seam) + `apps/rag/apps.py`; tests.
- **Modified:** `config/urls.py` (documents include), `config/settings/base.py` (`MEDIA_ROOT`/`MEDIA_URL`, `MAX_UPLOAD_MB`), `tests/smoke/test_endpoints_absent.py` (remove `/api/documents/upload/`; status/chat still absent).
- **Decisions to lock:** validate by extension AND content-type; max 10 MB; storage layout `uploads/user_<id>/`; task_id = Celery task id (status endpoint is slice 04); list/delete owner-scoping with 404.
