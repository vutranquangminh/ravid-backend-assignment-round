# Tasks — s03 Document upload

## 1. Settings & storage
- [x] 1.1 Add `MEDIA_ROOT`/`MEDIA_URL` (env) and `MAX_UPLOAD_MB` (default 10) to settings; tests point `MEDIA_ROOT` at a temp dir.

## 2. Document model
- [x] 2.1 `apps/documents/models.py`: `Document` (owner FK indexed, original_name, file FileField upload_to=user_path, content_type, size_bytes, status default UPLOADED, uploaded_at).
- [x] 2.2 `makemigrations documents`; check the migration in.

## 3. Upload + validation
- [x] 3.1 `serializers.py`: `DocumentUploadSerializer.validate_file` — extension in {.pdf,.txt,.md} AND content-type allowlist AND size ≤ MAX_UPLOAD_MB; bad type → exact brief message.
- [x] 3.2 `services.py`: `create_document(owner, uploaded_file)` saves file + row; `delete_document(owner, pk)` (owner-scoped) removes file + row.

## 4. Ingestion seam
- [x] 4.1 `apps/rag/tasks.py`: `@shared_task(bind=True) ingest_document(self, document_id)` placeholder — load doc, log `operation=ingest`, set status PROCESSING. (Real pipeline = slice 04.)

## 5. Views & routes
- [x] 5.1 `views.py`: `UploadView` (POST, JWT) → `202 {message, document_id, task_id}` / `400 {error}`; enqueue `ingest_document.delay(id)`.
- [x] 5.2 `DocumentListView` (GET, JWT) → caller-owned only; `DocumentDeleteView` (DELETE `<id>`, JWT) → 204; cross-user/missing → 404.
- [x] 5.3 `urls.py` + include in `config/urls.py` (`/api/documents/upload/`, `/api/documents/`, `/api/documents/<id>/`).

## 6. Tests
- [x] 6.1 Upload happy: PDF/TXT/MD each → 202 + document_id + task_id; file saved under `uploads/user_<id>/`; Document row created with owner.
- [x] 6.2 Upload validation: `.exe`/unknown type → 400 exact message; oversize → 400; no token → 401.
- [x] 6.3 Isolation: user A cannot GET user B's doc in the list; DELETE of B's doc by A → 404; A deletes own → 204 + file gone.
- [x] 6.4 Regression: `/api/documents/status/`, `/api/chat/query/` still ABSENT (404); `/api/documents/upload/` now present.
- [x] 6.5 Unit: serializer validation matrix; services create/delete.

## 7. Validate & deliver
- [x] 7.1 `manage.py check` clean; `pytest` green; `pre-commit` clean.
- [x] 7.2 `docs/02-features/03-document-upload/{test_matrix,validation-report,pull_request}.md`.
- [x] 7.3 PR into `main` (base main, no branch deletion); `openspec archive s03` after merge.
