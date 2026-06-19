# Pull Request — 04 Ingestion pipeline (chunk → embed → Chroma) + status

## Progress Snapshot
- **Workstream:** 04 — ingestion pipeline (RAVID Part 2, completes it)
- **Branch (source → target):** `feature/04-ingestion-pipeline-chunk-embed-chroma` → `main`
- **OpenSpec change:** `s04-ingestion-pipeline-chunk-embed-chroma` (validated)
- **Status:** ready for review
- **Validation:** `manage.py check` clean · `pytest` 151 passed · `ruff` clean · `pre-commit` clean
- **Next:** slice 05 — RAG chat query (OpenRouter)

## Summary
Turns the slice-03 placeholder into a real async pipeline: extract (pypdf/UTF-8) → split (1000/150) → embed → upsert into a **per-user Chroma collection** `user_<id>`. Adds the `IngestionJob` state machine (DB row = source of truth) and `GET /api/documents/status/` with the brief's PROCESSING/SUCCESS/FAILURE bodies. Failures surface in logs AND the job; deleting a document removes its vectors.

## Scope
**In:** `IngestionJob` model, real `ingest_document` task, pipeline/embeddings/vectorstore modules, status endpoint, upload+delete integration, offline tests.
**Out:** chat/retrieval (slice 05), chroma compose service (slice 07).

## Key Changes
- `apps/rag/{models,embeddings,vectorstore,pipeline,tasks,views,urls}.py` + `migrations/0001_initial.py`.
- `apps/documents/views.py` — upload creates `IngestionJob`; delete removes vectors.
- `config/settings/{base,test}.py` — Chroma/embedding/splitter config; stub embeddings + temp Chroma in tests.
- `tests/integration/test_ingestion_api.py`, `tests/unit/test_pipeline_units.py`; regression updated (status now present).

## Reviewer Steps
```bash
.venv/bin/pip install -e '.[rag]'
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
.venv/bin/python -m pytest -q             # 151 passed
pre-commit run --all-files
```
Then: upload → `GET /api/documents/status/?task_id=<id>` → `SUCCESS`; try another user's task_id → `404`.

## Validation
See `docs/02-features/04-ingestion-pipeline/validation-report.md`.

## Submission Readiness
- [x] OpenSpec change validated
- [x] Part 2 ingestion + status contract exact
- [x] Per-user vector isolation (collection + 404)
- [x] Failures surfaced (logs + job), not swallowed
- [x] Tests green (151), check clean, lint/hooks clean
- [ ] Merged to main (awaiting review)
- [ ] `openspec archive s04-...` after merge
