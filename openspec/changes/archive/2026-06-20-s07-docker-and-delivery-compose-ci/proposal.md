# Proposal — s07 Docker & delivery (compose + CI + docs)

> Workstream **07** · branch `feature/07-docker-and-delivery-compose-ci` · delivery artifacts in `docs/02-features/07-docker-and-delivery/`. Implements RAVID brief **Part 4**.

## Why

The reviewer must be able to run the whole system with a single command and read clear API docs. This slice packages everything built in slices 01–05 into Docker Compose (web, db, redis, celery, chroma, and an observability dashboard), wires real production settings (Postgres + real Celery + Chroma server + real embeddings/OpenRouter), adds live API documentation, and a CI pipeline.

## What Changes

- **`docker/django/Dockerfile`** — `python:3.12-slim`, installs the package with the `rag` extra + `gunicorn`; non-root user; entrypoint runs migrations then serves via gunicorn.
- **`compose.yaml`** — services: `web` (gunicorn), `db` (postgres), `redis`, `celery` (worker), `chroma` (chromadb server), `loki`, `alloy`, `grafana` (the dashboard). Healthcheck-gated `depends_on`, named volumes (`pg_data`, `media`, `chroma_data`, `grafana_data`), loopback-bound infra ports (chroma `127.0.0.1:8001:8000` to avoid the web:8000 clash), env from `.env`.
- **`config/settings/production.py`** — env-driven: Postgres, real Celery (Redis broker, NOT eager), Chroma **server** via `CHROMA_HOST`, real embeddings + OpenRouter, `DEBUG=False`, `ALLOWED_HOSTS` from env, JSON logging to stdout.
- **Chroma client dual-mode** — `vectorstore` uses `chromadb.HttpClient(CHROMA_HOST, CHROMA_PORT)` when `CHROMA_HOST` is set (Docker), else the `PersistentClient` (local/test). External contract unchanged.
- **Observability** — `docker/{alloy/config.alloy, loki/config.yaml, grafana/provisioning + dashboard json}` so Django + Celery JSON logs flow to Grafana (folds in the Part-4 dashboard requirement).
- **API docs** — add `drf-spectacular`: live OpenAPI at `/api/schema/` + Swagger UI at `/api/docs/` (public), generated from the real DRF views; keep the hand-written `docs/01-architecture/api_contract.yaml`; add a Postman/Bruno collection under `docs/api/`.
- **CI** — `compose.ci.yaml` (lean: db, redis, app with stub keys) and `.github/workflows/pr-ci.yml` (repo checks → tests → container build/smoke).
- **README** — full setup & run instructions (`docker compose up`), env setup, API-docs links, and the per-user isolation note.

## Capabilities

### New Capabilities
- `docker-delivery`: a one-command containerized stack, production settings, live API docs, and CI — the system is runnable and reviewable end-to-end.

### Modified Capabilities
- (none — `vectorstore` gains an HttpClient mode but its public functions are unchanged.)

## Impact

- **New:** `docker/**`, `compose.yaml`, `compose.ci.yaml`, `config/settings/production.py`, `.github/workflows/pr-ci.yml`, `scripts/ci/*.sh`, `docs/api/*` (Postman + README), `gunicorn`+`drf-spectacular` deps.
- **Modified:** `apps/rag/vectorstore.py` (HttpClient mode), `config/urls.py` (schema/docs routes), `config/settings/base.py` (drf-spectacular), root `README.md`.
- **Decisions:** chroma server + HttpClient in Docker; `config.settings.production`; gunicorn; drf-spectacular for live docs; CI stays network-free (stub keys, settings.test).
- **Constraint:** the Docker daemon isn't running in the authoring env, so validation is static (`docker compose config`, structure tests) + documented manual run steps; full `docker compose up` is the reviewer's step.
