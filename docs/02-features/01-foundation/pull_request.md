# Pull Request — 01 Foundation (Django + LangChain bootstrap)

## Progress Snapshot
- **Workstream:** 01 — foundation Django/DRF/Celery bootstrap
- **Branch (source → target):** `feature/01-foundation-django-langchain-bootstrap` → `main` (stacked on `feature/00-...` until it merges)
- **OpenSpec change:** `s01-foundation-django-langchain-bootstrap` (validated; tasks 1–7 complete)
- **Status:** ready for review
- **Validation:** `manage.py check` clean · `pytest` 41 passed · `pre-commit` clean
- **Next:** slice 02 — authentication (register/login + JWT)

## Summary
First runnable slice: a bootable Django 5 + DRF + Celery skeleton with structured JSON logging, env-driven settings, an offline key-free test posture, and a single public `GET /api/health/` endpoint. No business features yet — those land in slices 02–05.

## Scope
**In:** project package, split settings, Celery wiring, logging + request-id middleware, env helpers, health endpoint, dependency manifest (core + `rag`/`dev` extras), offline test posture, smoke/unit/regression tests.
**Out:** auth, models, upload, ingestion, chat, Docker (each its own slice).

## Key Changes
- `config/` — settings `base`/`local`/`test`, `celery.py`, `urls.py`, `wsgi`/`asgi`.
- `apps/{accounts,documents,rag}` placeholders + `apps/common` (`env.py`, `middleware.py`, health `views.py`/`urls.py`).
- `pyproject.toml` — `[build-system]` + `[project]` (core deps) + `rag`/`dev` extras + pytest config (slice-00 ruff/commitizen preserved).
- `tests/{smoke,unit}` — boot, health, env helpers, absent-endpoint regression.

## Reviewer Steps
```bash
python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e '.[dev]'
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
.venv/bin/python -m pytest -q
pre-commit run --all-files
```
Expect: check clean, 41 passed, hooks pass. Hit `GET /api/health/` → `{"status":"ok"}`.

## Validation
See `docs/02-features/01-foundation/validation-report.md`.

## Submission Readiness
- [x] OpenSpec change validated, tasks complete
- [x] Tests green (41), system check clean
- [x] pre-commit / commit lint clean
- [ ] Merged to main (awaiting review; stacked on slice 00)
- [ ] `openspec archive s01-...` after merge
