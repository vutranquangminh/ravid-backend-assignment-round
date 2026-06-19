# Design — s01 Foundation

## Context

Greenfield repo after slice 00 (specs + agent OS + architecture docs only). Architecture decisions are already frozen in `docs/01-architecture/*` and `.agents/references/assessment-decisions.md`; this design only covers how the bootstrap realizes them. Target runtime: Python 3.12, Django 5.x, DRF, Celery on Redis, Postgres in Docker (sqlite acceptable for local/test). Heavy ML deps (chromadb, langchain-huggingface/torch) are declared now but **not exercised** until slices 03–05, so tests must not import them.

## Goals / Non-Goals

**Goals:**
- A `manage.py check`-clean, bootable project with split settings and a working `/api/health/`.
- Structured JSON logs with a per-request `request_id` from day one (so observability in slice 06/07 is just shipping, not retrofitting).
- An offline, key-free test posture reused by every later slice.
- Dependency manifest complete enough that later slices only add code, not deps.

**Non-Goals:**
- No auth, no models with business meaning, no upload/ingestion/chat (own slices).
- No Docker/compose (slice 07). Local dev may use sqlite + a local Redis or eager Celery.
- No real Chroma/embedding/OpenRouter calls.

## Decisions

- **Settings split:** `base.py` (shared, reads env), `local.py` (DEBUG, sqlite fallback, console+JSON logs), `test.py` (eager Celery, temp Chroma dir, fast password hasher, stub seams). `DJANGO_SETTINGS_MODULE` defaults to `config.settings.local`.
- **Env helpers in `apps/common/env.py`:** `env(key, default)`, `env_bool`, `env_int`, `env_list` reading `os.environ`; no hard dependency on django-environ to keep deps lean.
- **Logging:** `python-json-logger` formatter on the root + `celery` loggers; a `RequestIdMiddleware` generates/propagates `request_id` (uuid4) and a `RequestLoggingMiddleware` logs method/path/status/duration_ms. High-cardinality ids stay in the JSON payload (per `observability.md`), never as labels.
- **App layout:** each app has `apps.py` with an explicit `AppConfig` (`name = "apps.<x>"`), `__init__.py`. `accounts/documents/rag` are placeholders; `common` carries shared infra. URLs are namespaced; root `config/urls.py` includes `/api/health/` now and reserves `/api/...` includes (commented) for later slices.
- **Health endpoint:** a function-based DRF/`JsonResponse` view returning `{"status":"ok"}` 200, `AllowAny`. Cheap liveness, no DB hit.
- **Celery:** `config/celery.py` defines the app reading `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`; autodiscover tasks. In tests, `task_always_eager=True`.
- **Stub seams:** define thin client wrappers (`apps/rag/clients.py` placeholder or `apps/common`) so slices 04/05 inject stubs in `settings.test` rather than monkeypatching deep internals.

## Risks / Trade-offs

- **Heavy deps vs CI speed:** torch (via langchain-huggingface) is large. Mitigation: tests never import ML libs; CI installs the `dev` extra but the suite stays import-light; full ML install is validated when slice 03/04 needs it.
- **sqlite-vs-postgres drift:** local/test use sqlite for speed; Docker uses postgres (slice 07). Mitigation: avoid postgres-only fields in models; document the choice.
- **Env-helper vs django-environ:** rolling our own is lean but less battle-tested. Mitigation: keep helpers tiny and unit-tested.
