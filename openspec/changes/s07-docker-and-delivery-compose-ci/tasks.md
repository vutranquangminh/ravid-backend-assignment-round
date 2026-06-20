# Tasks — s07 Docker & delivery

## 1. Dependencies & settings
- [ ] 1.1 Add `gunicorn` + `drf-spectacular` to `[project.dependencies]`; install.
- [ ] 1.2 `config/settings/production.py` — env-driven Postgres, real Celery (not eager), Chroma server (`CHROMA_HOST`), real embeddings/OpenRouter, DEBUG off, ALLOWED_HOSTS, stdout JSON logs.
- [ ] 1.3 `base.py`: add `drf-spectacular` (`DEFAULT_SCHEMA_CLASS`, `SPECTACULAR_SETTINGS`).

## 2. Chroma dual-mode
- [ ] 2.1 `apps/rag/vectorstore.py`: `_client()` uses `HttpClient` when `CHROMA_HOST` set, else `PersistentClient`. Public API unchanged.

## 3. API docs
- [ ] 3.1 `config/urls.py`: `/api/schema/` (SpectacularAPIView) + `/api/docs/` (Swagger UI), AllowAny.
- [ ] 3.2 `docs/api/ravid.postman_collection.json` + `docs/api/README.md` (how to use the collection / Swagger).

## 4. Dockerfile & entrypoint
- [ ] 4.1 `docker/django/Dockerfile` (python:3.12-slim, install `.[rag]`+gunicorn, non-root).
- [ ] 4.2 `docker/django/entrypoint.sh` (migrate → gunicorn); celery uses the same image.

## 5. Compose
- [ ] 5.1 `compose.yaml` — web, db, redis, celery, chroma, loki, alloy, grafana; healthchecks; depends_on service_healthy; volumes; loopback infra ports; env_file.
- [ ] 5.2 `compose.ci.yaml` — lean (db, redis, app) with sentinel keys + settings.test.
- [ ] 5.3 `.env.example` — add POSTGRES_*, CHROMA_HOST/PORT, ALLOWED_HOSTS, DEBUG, gunicorn/grafana vars.

## 6. Observability configs
- [ ] 6.1 `docker/alloy/config.alloy`, `docker/loki/config.yaml`, `docker/grafana/provisioning/{datasources,dashboards}/*`, `docker/grafana/dashboards/overview.json`.

## 7. CI
- [ ] 7.1 `.github/workflows/pr-ci.yml` (repo checks → pytest → container build/smoke), network-free.
- [ ] 7.2 `scripts/ci/*.sh` helpers as needed.

## 8. README
- [ ] 8.1 Rewrite `README.md`: overview, architecture, `docker compose up` run steps, env setup, API-docs links (`/api/docs/`), test instructions, per-user isolation note, branch/slice map.

## 9. Tests (offline, structure/delivery) + keep suite green
- [ ] 9.1 Parse `compose.yaml`: required services present, healthchecks defined, named volumes, chroma loopback port.
- [ ] 9.2 Assert Dockerfile, entrypoint, observability configs, `.env.example` keys, Postman collection exist.
- [ ] 9.3 `/api/schema/` 200 + valid OpenAPI; `/api/docs/` 200.
- [ ] 9.4 `vectorstore` selects HttpClient when CHROMA_HOST set (monkeypatch), PersistentClient otherwise.
- [ ] 9.5 `docker compose config` parses (if daemon present); otherwise YAML-parse validation.

## 10. Validate & deliver
- [ ] 10.1 `manage.py check`; full `pytest` green; `ruff check`; `pre-commit`; `docker compose config` (static).
- [ ] 10.2 `docs/02-features/07-docker-and-delivery/{test_matrix,validation-report,pull_request}.md`.
- [ ] 10.3 PR into `main` (base main, no branch deletion); `openspec archive s07` after merge.
