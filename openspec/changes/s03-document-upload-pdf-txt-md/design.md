# Design — s03 Document upload

## Context

Slice 02 established JWT auth and `request.user`. This slice introduces the first owned resource (`Document`) and the upload endpoint from Part 2. Ingestion internals (parse/chunk/embed/Chroma) and the status endpoint are slice 04; this slice defines the model, the upload contract, the per-user isolation rules, and the Celery enqueue seam so slice 04 only fills in the task body and adds `/api/documents/status/`.

## Goals / Non-Goals

**Goals:**
- Exact brief upload behaviour: multipart `file`, `202 {message, document_id, task_id}`, the exact bad-format error string.
- Strict validation (type by extension AND content-type; size ≤ 10 MB) BEFORE any work is queued.
- Per-user isolation baked into list/delete: a user can only see/delete their own docs; others' ids → 404.
- Files on disk under `uploads/user_<id>/`, never in the DB.

**Non-Goals:**
- No text extraction, chunking, embedding, or Chroma writes (slice 04).
- No `/api/documents/status/` endpoint yet (slice 04).
- No Docker/volumes (slice 07) — local/test use `MEDIA_ROOT` (temp dir in tests).

## Decisions

- **Model:** `Document(owner=FK(User, on_delete=CASCADE, db_index=True), original_name, file=FileField(upload_to=user_path), content_type, size_bytes, status=CharField default "UPLOADED", uploaded_at=auto_now_add)`. `user_path(instance, filename)` → `uploads/user_<owner_id>/<uuid>_<filename>`.
- **Validation order:** in the serializer/`validate_file`: (1) extension in `{.pdf,.txt,.md}`; (2) content-type in an allowlist (`application/pdf`, `text/plain`, `text/markdown`, `text/x-markdown`, plus tolerant fallbacks); (3) size ≤ `MAX_UPLOAD_MB`. Any failure → `400 {"error":"Invalid file format. Only PDF, TXT, and Markdown files are allowed."}` for type, and a clear size message for size. Validation happens before the file is persisted or the task queued (M-006: never queue junk).
- **Upload flow:** `services.create_document(owner, uploaded_file)` saves the file + row atomically, then the view calls `ingest_document.delay(document.id)` and returns `202` with `document_id=document.id` and `task_id=result.id`. The `task_id` is the Celery task id (the status endpoint that queries it is slice 04).
- **Ingestion seam:** `apps/rag/tasks.py::ingest_document(self, document_id)` is a `@shared_task(bind=True)` placeholder this slice — loads the Document, logs `operation=ingest document_id=...`, sets `status="PROCESSING"` (then leaves it). Slice 04 replaces the body with the real pipeline + an `IngestionJob` row. Eager mode runs it inline in tests.
- **Isolation:** all document querysets filter `owner=request.user`. `GET /api/documents/` returns only the caller's docs. `DELETE /api/documents/<id>/` uses `get_object_or_404(Document, pk=pk, owner=request.user)` → cross-user or missing → 404. (M-005 baseline.)
- **Storage settings:** `MEDIA_ROOT` (env, default `<base>/media`), `MEDIA_URL=/media/`. Tests set `MEDIA_ROOT` to a temp dir; cleanup via tmp.

## Risks / Trade-offs

- **Content-type spoofing:** browsers/curl can send wrong MIME types; we check extension AND content-type but don't sniff magic bytes this slice. Mitigation: extension is authoritative; slice 04's parser will fail loudly on truly-corrupt files and surface FAILURE.
- **task_id vs IngestionJob:** returning the Celery id now means slice 04 must keep that id queryable (store it on the IngestionJob). Documented so 04 honors it.
- **Orphan files on delete:** deleting a Document must also remove its file and (later) its vectors. This slice removes the file; vector cleanup is wired in slice 04 when Chroma exists.
