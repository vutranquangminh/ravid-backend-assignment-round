# Pull Request — 07 Docker & delivery (compose + CI + API docs)

## Progress Snapshot
- **Workstream:** 07 — Docker & delivery (RAVID Part 4)
- **Branch (source → target):** `feature/07-docker-and-delivery-compose-ci` → `main`
- **OpenSpec change:** `s07-docker-and-delivery-compose-ci` (validated)
- **Status:** ready for review
- **Validation:** test+production `check` clean · `pytest` 620 passed · `ruff` clean · `docker compose config` valid · `pre-commit` clean
- **Next:** slice 08 — bonus (chat_id continuation + SSE), optional

## Summary
Packages the whole system for one-command run and review: Docker Compose (web, celery, db, redis, chroma, grafana+loki+alloy), a production settings module, live API docs (Swagger), a CI pipeline, and a reviewer README. **Completes RAVID Part 4** → Parts 1–4 all delivered.

## Scope
**In:** Dockerfile + entrypoint, `compose.yaml` + `compose.ci.yaml`, `config/settings/production.py`, chroma HttpClient dual-mode, observability configs, `pr-ci.yml` + ci scripts, `drf-spectacular` (`/api/schema/`, `/api/docs/`), Postman collection, README rewrite, 48 delivery/vectorstore tests.
**Out:** live container run (reviewer step — no Docker daemon in authoring env); bonus chat_id/SSE (slice 08).

## Key Changes
- `docker/django/{Dockerfile,entrypoint.sh}`, `docker/{alloy,loki,grafana}/**`.
- `compose.yaml` (8 services, health-gated), `compose.ci.yaml` (lean CI).
- `config/settings/production.py`; `apps/rag/vectorstore.py` dual-mode client.
- `config/settings/base.py` + `config/urls.py` (drf-spectacular); `docs/api/` (Postman + README).
- `.github/workflows/pr-ci.yml`, `scripts/ci/*.sh`; `.env.example`; `README.md` (reviewer guide).
- `tests/integration/test_delivery.py`, `tests/unit/test_vectorstore_modes.py`.

## Reviewer Steps
```bash
cp .env.example .env          # set OPENROUTER_API_KEY=sk-or-...
docker compose up --build      # web :8000, swagger /api/docs/, grafana :3000
# offline checks:
.venv/bin/pip install -e '.[rag,dev]'
.venv/bin/python -m pytest -q  # 620 passed
docker compose config          # valid
```

## Validation
See `docs/02-features/07-docker-and-delivery/validation-report.md` (note: live container run is the reviewer's step — daemon unavailable while authoring).

## Submission Readiness
- [x] OpenSpec change validated
- [x] Compose stack (web/db/redis/celery/dashboard + chroma) — health-gated
- [x] Live API docs + Postman + README run steps
- [x] CI pipeline; production settings import-clean
- [x] Tests green (620), ruff/hooks clean, compose config valid
- [ ] Reviewer confirms `docker compose up` live
- [ ] Merged to main; `openspec archive s07-...` after merge
