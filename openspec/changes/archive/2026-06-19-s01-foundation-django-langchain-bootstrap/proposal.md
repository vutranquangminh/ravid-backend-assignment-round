# Proposal — s01 Foundation: Django + LangChain bootstrap

> Workstream **01** · branch `feature/01-foundation-django-langchain-bootstrap` · delivery artifacts in `docs/02-features/01-foundation/`.

## Why

The foundation branch (00) established the spec/agent/docs baseline but contains **no runnable application**. Every later slice (auth, upload, ingestion, chat) needs a working Django + DRF + Celery project to build on, plus an **offline, key-free test posture** so the suite and CI never hit the network. This slice creates that skeleton — and nothing more — so subsequent slices are pure vertical features.

## What Changes

- Create the Django 5.x project package `config/` with **split settings** (`base`/`local`/`test`), `celery.py`, root `urls.py`, `wsgi.py`/`asgi.py`, and `manage.py`.
- Create empty-but-wired app packages `apps/{accounts,documents,rag,common}` (no models/endpoints yet — those arrive in their own slices).
- Implement cross-cutting infrastructure in `apps/common`: **structured JSON logging**, a **request-id + request-logging middleware**, and typed **env helpers** (`env`, `env_bool`, `env_int`, `env_list`).
- Add a single testable **`GET /api/health/`** endpoint (liveness) so the skeleton is verifiable end-to-end.
- Promote `pyproject.toml` to a full project: `[build-system]` + `[project]` runtime deps (django, djangorestframework, djangorestframework-simplejwt, celery[redis], psycopg, langchain, langchain-text-splitters, langchain-huggingface, chromadb, pypdf, python-json-logger) and a `dev` extra (pytest, pytest-django, pytest-cov, ruff).
- Wire the **offline test posture** in `config/settings/test.py`: `CELERY_TASK_ALWAYS_EAGER=True`, a temp/in-memory Chroma persist dir, and stub seams for the embedding + OpenRouter clients.
- Add smoke tests (Django boots, `/api/health/` returns 200) and a **regression test** asserting the upload/chat endpoints are still ABSENT.

## Capabilities

### New Capabilities
- `platform-foundation`: the runnable Django/DRF/Celery runtime baseline — settings, logging, env config, health endpoint, and the offline test posture that all later slices depend on.

### Modified Capabilities
- (none — first runnable slice)

## Impact

- **New code:** `manage.py`, `config/**`, `apps/{accounts,documents,rag,common}/**`, `tests/{smoke,unit}/**`.
- **Modified:** `pyproject.toml` (adds `[build-system]`/`[project]`; tooling config from slice 00 preserved).
- **Dependencies:** introduces the full runtime + dev dependency set.
- **No behavioral surface** beyond `/api/health/`; auth/upload/ingestion/chat remain unimplemented by design.
