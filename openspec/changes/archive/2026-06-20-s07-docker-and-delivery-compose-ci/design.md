# Design — s07 Docker & delivery

## Context

Slices 01–05 run locally/offline. Part 4 requires a one-command stack, README, and API docs. Local/test use sqlite + eager Celery + a Chroma PersistentClient; Docker needs Postgres + a real Celery worker + a Chroma server + real embeddings/OpenRouter. The Docker daemon is unavailable in the authoring environment, so this slice is validated statically (compose parse + structure tests) with documented manual run steps.

## Goals / Non-Goals

**Goals:**
- `docker compose up` brings up web + db + redis + celery + chroma + grafana(+loki+alloy), health-gated.
- A production settings module driven entirely by env vars.
- Live, accurate API docs (Swagger UI) plus the OpenAPI file and a Postman collection.
- CI that runs the suite network-free and a container build/smoke.
- Keep the full offline test suite green; add structure/delivery tests.

**Non-Goals:**
- No real LLM/embedding calls in CI or tests (stubs stay).
- No production secrets committed (`.env` gitignored; `.env.example` documents keys).
- No k8s / cloud deploy.

## Decisions

- **Dockerfile:** `python:3.12-slim`; system deps for psycopg/pypdf as needed; `pip install -e '.[rag]' gunicorn`; create a non-root user; `ENTRYPOINT` script: `python manage.py migrate --noinput` then `gunicorn config.wsgi:application -b 0.0.0.0:8000`. Celery service reuses the same image with command `celery -A config worker -l info`.
- **Settings module:** `config/settings/production.py` (imports base): `DEBUG=env_bool("DEBUG", False)`, Postgres from `POSTGRES_*`/`DATABASE_URL`, `CELERY_TASK_ALWAYS_EAGER=False`, broker/result = `REDIS_URL`, `CHROMA_HOST`/`CHROMA_PORT` set (→ HttpClient), real embeddings + OpenRouter (no stub flags), `ALLOWED_HOSTS=env_list`, stdout JSON logs. Compose sets `DJANGO_SETTINGS_MODULE=config.settings.production`.
- **Chroma dual-mode (`vectorstore._client`):** if `getattr(settings,"CHROMA_HOST",None)` → `chromadb.HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT), settings=Settings(anonymized_telemetry=False))`; else `PersistentClient(path=CHROMA_PERSIST_DIR, ...)`. Singleton reset-safe. Tests/local stay on PersistentClient (no CHROMA_HOST).
- **compose.yaml topology:** healthchecks — db `pg_isready`, redis `redis-cli ping`, chroma `GET /api/v1/heartbeat`, web `GET /api/health/`, grafana `/api/health`. `depends_on: condition: service_healthy`. Volumes: `pg_data`, `media` (shared web+celery), `chroma_data`, `grafana_data`. Ports: web `8000:8000`; infra bound to `127.0.0.1` (chroma `8001:8000`, grafana `3000:3000`, others internal). Env via `env_file: .env`.
- **Observability:** mirror the architecture docs — Alloy scrapes container stdout (Docker socket), parses JSON, promotes `service` to a low-cardinality Loki label; Loki single-binary filesystem; Grafana provisioned datasource + a dashboard (log stream by service, error count, slowest ops by duration_ms). Folds the Part-4 dashboard requirement in here.
- **API docs:** `drf-spectacular` → `SpectacularAPIView` at `/api/schema/` and `SpectacularSwaggerView` at `/api/docs/` (both AllowAny). `SPECTACULAR_SETTINGS` title/desc. Keep `docs/01-architecture/api_contract.yaml`; add `docs/api/ravid.postman_collection.json` + `docs/api/README.md`.
- **CI:** `compose.ci.yaml` (db, redis, app; `OPENROUTER_API_KEY=sentinel`, settings.test). `.github/workflows/pr-ci.yml`: job 1 repo checks (ruff, openspec validate, pre-commit), job 2 pytest matrix, job 3 container build + `manage.py check`/migrate/health smoke. Network-free.
- **Tests (delivery/structure, offline):** parse `compose.yaml` (PyYAML, now installable as a dev dep) and assert required services/healthchecks/volumes; assert Dockerfile + observability configs + `.env.example` keys exist; assert `/api/schema/` and `/api/docs/` return 200; assert `vectorstore` selects HttpClient when `CHROMA_HOST` is set (monkeypatch settings) and PersistentClient otherwise.

## Risks / Trade-offs

- **No live container run here:** mitigated by static `docker compose config` validation + structure tests + a precise README; the reviewer runs the real stack.
- **Chroma server API path** (`/api/v1/heartbeat`) varies by chromadb version: pin the `chromadb/chroma` image to a tag matching the client (1.5.x) and document it.
- **drf-spectacular schema generation** can warn on custom views: add minimal `@extend_schema` where needed so `/api/schema/` is clean.
- **Two settings for DB** (sqlite local/test vs Postgres prod): avoid backend-specific fields (already done); document.
