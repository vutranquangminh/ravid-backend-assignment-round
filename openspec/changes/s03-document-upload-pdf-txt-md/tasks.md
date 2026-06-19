# Tasks — s03 Document upload

## 1. Settings & storage
- [ ] 1.1 Add `MEDIA_ROOT`/`MEDIA_URL` (env) and `MAX_UPLOAD_MB` (default 10) to settings; tests point `MEDIA_ROOT` at a temp dir.

## 2. Document model
- [ ] 2.1 `apps/documents/models.py`: `Document` (owner FK indexed, original_name, file FileField upload_to=user_path, content_type, size_bytes, status default UPLOADED, uploaded_at).
- [ ] 2.2 `makemigrations documents`; check the migration in.

## 3. Upload + validation
- [ ] 3.1 `serializers.py`: `DocumentUploadSerializer.validate_file` — extension in {.pdf,.txt,.md} AND content-type allowlist AND size ≤ MAX_UPLOAD_MB; bad type → exact brief message.
- [ ] 3.2 `services.py`: `create_document(owner, uploaded_file)` saves file + row; `delete_document(owner, pk)` (owner-scoped) removes file + row.

## 4. Ingestion seam
- [ ] 4.1 `apps/rag/tasks.py`: `@shared_task(bind=True) ingest_document(self, document_id)` placeholder — load doc, log `operation=ingest`, set status PROCESSING. (Real pipeline = slice 04.)

## 5. Views & routes
- [ ] 5.1 `views.py`: `UploadView` (POST, JWT) → `202 {message, document_id, task_id}` / `400 {error}`; enqueue `ingest_document.delay(id)`.
- [ ] 5.2 `DocumentListView` (GET, JWT) → caller-owned only; `DocumentDeleteView` (DELETE `<id>`, JWT) → 204; cross-user/missing → 404.
- [ ] 5.3 `urls.py` + include in `config/urls.py` (`/api/documents/upload/`, `/api/documents/`, `/api/documents/<id>/`).

## 6. Tests
- [ ] 6.1 Upload happy: PDF/TXT/MD each → 202 + document_id + task_id; file saved under `uploads/user_<id>/`; Document row created with owner.
- [ ] 6.2 Upload validation: `.exe`/unknown type → 400 exact message; oversize → 400; no token → 401.
- [ ] 6.3 Isolation: user A cannot GET user B's doc in the list; DELETE of B's doc by A → 404; A deletes own → 204 + file gone.
- [ ] 6.4 Regression: `/api/documents/status/`, `/api/chat/query/` still ABSENT (404); `/api/documents/upload/` now present.
- [ ] 6.5 Unit: serializer validation matrix; services create/delete.

## 7. Validate & deliver
- [ ] 7.1 `manage.py check` clean; `pytest` green; `pre-commit` clean.
- [ ] 7.2 `docs/02-features/03-document-upload/{test_matrix,validation-report,pull_request}.md`.
- [ ] 7.3 PR into `main` (base main, no branch deletion); `openspec archive s03` after merge.
