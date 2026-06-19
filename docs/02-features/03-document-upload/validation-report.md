# Validation Report — 03 Document upload

> Branch `feature/03-document-upload-pdf-txt-md` (base `main`). Env: `.venv`, `.[dev]`. Temp `MEDIA_ROOT` in tests.

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `makemigrations documents` | Model migration | ✅ `0001_initial` (Create model Document) | checked in |
| `manage.py check` | Django system check | ✅ `System check identified no issues (0 silenced).` | re-run independently |
| `python -m pytest -q` | Full suite | ✅ `115 passed` | 40 new upload tests + 75 prior |
| `pre-commit run --all-files` | Lint/format/hooks | ✅ all pass | — |

## Brief compliance (Part 2 — upload)

| Aspect | Brief | Implemented |
|--------|-------|-------------|
| `POST /api/documents/upload/` | multipart `file`, `202 {message,document_id,task_id}` | ✅ exact |
| Allowed types | PDF, TXT, Markdown only | ✅ extension + content-type |
| Reject message | "Invalid file format. Only PDF, TXT, and Markdown files are allowed." | ✅ byte-for-byte |
| Async hand-off | accepted for asynchronous ingestion | ✅ Celery enqueue, task_id returned |

## Failures Or Gaps

- **Ingestion body is a placeholder** — `apps/rag/tasks.py::ingest_document` only logs + sets `status=PROCESSING`. Real parse/chunk/embed/Chroma + the `IngestionJob` model + `/api/documents/status/` land in slice 04 (which must keep the returned Celery `task_id` queryable).
- **No magic-byte sniffing** — type checked by extension + content-type only; slice 04's parser surfaces truly-corrupt files as FAILURE.
- `/api/chat/query/` absent (slice 05).

## Mistake check

`No active mistake repeated.` (M-005: every document queryset filtered by `owner=request.user`, cross-user → 404; M-006: validation runs BEFORE persisting/queuing; M-008: no file contents or secrets logged — only ids/metadata.)
