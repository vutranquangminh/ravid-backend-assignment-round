# Pull Request — 03 Document upload (PDF / TXT / MD)

## Progress Snapshot
- **Workstream:** 03 — document upload (RAVID Part 2, upload half)
- **Branch (source → target):** `feature/03-document-upload-pdf-txt-md` → `main` (direct)
- **OpenSpec change:** `s03-document-upload-pdf-txt-md` (validated)
- **Status:** ready for review
- **Validation:** `manage.py check` clean · `pytest` 115 passed · `pre-commit` clean
- **Next:** slice 04 — ingestion pipeline (chunk → embed → Chroma) + `/api/documents/status/`

## Summary
Authenticated multipart upload that validates type (PDF/TXT/MD) and size (≤10 MB), stores the file per-user, records a `Document`, and enqueues ingestion — returning `202 {message, document_id, task_id}`. Adds per-user list/delete with cross-user `404` isolation. Ingestion body is a placeholder; slice 04 fills it.

## Scope
**In:** `Document` model, upload/list/delete endpoints, type/size validation, per-user storage + isolation, Celery ingestion seam, tests.
**Out:** real parse/chunk/embed/Chroma, `/api/documents/status/`, chat (later slices).

## Key Changes
- `apps/documents/{models,serializers,services,views,urls}.py` + `migrations/0001_initial.py`.
- `apps/rag/tasks.py` — `ingest_document` placeholder task.
- `config/settings/base.py` (`MEDIA_ROOT/URL`, `MAX_UPLOAD_MB`), `config/settings/test.py` (temp MEDIA_ROOT), `config/urls.py`.
- `tests/integration/test_document_upload_api.py`, `tests/unit/test_document_units.py`; regression updated (upload now present).

## Reviewer Steps
```bash
.venv/bin/pip install -e '.[dev]'
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
.venv/bin/python -m pytest -q             # 115 passed
pre-commit run --all-files
```
Then: login → `POST /api/documents/upload/` with a PDF (`-F file=@x.pdf`, Bearer token) → `202`; `GET /api/documents/`; try another user's id on DELETE → `404`.

## Validation
See `docs/02-features/03-document-upload/validation-report.md`.

## Submission Readiness
- [x] OpenSpec change validated
- [x] Upload contract + exact reject message
- [x] Per-user isolation (404 cross-user)
- [x] Tests green (115), check clean, hooks clean
- [ ] Merged to main (awaiting review)
- [ ] `openspec archive s03-...` after merge
