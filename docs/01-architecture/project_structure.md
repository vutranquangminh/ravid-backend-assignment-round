# Project Structure

## Objective

Define a simple, reviewable Django project layout for the R.A.V.I.D. RAG
backend that supports authentication, document upload, asynchronous ingestion,
owner-scoped retrieval, and LLM chat without unnecessary abstraction.

## Proposed Layout

```text
.
├── compose.yaml
├── compose.ci.yaml
├── Makefile
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── scripts/
│   ├── dev/
│   │   └── run_local.sh
│   └── ci/
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── test.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py / asgi.py
├── apps/
│   ├── accounts/
│   ├── documents/
│   ├── rag/
│   └── common/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── smoke/
├── docs/
├── openspec/
├── .github/
├── docker/
│   ├── django/
│   ├── alloy/
│   ├── loki/
│   └── grafana/
└── manage.py
```

Note the CSV-era apps are renamed for RAVID: `apps/files` -> `apps/documents`
and `apps/operations` -> `apps/rag`.

## App Responsibilities

### `apps/accounts`

- registration and login
- auth serializers and views
- JWT integration points (`djangorestframework-simplejwt`)
- per-user credit balance (model field or small related model) and its
  decrement helper

### `apps/documents`

- `Document` metadata model (owner FK, original name, storage path, content
  type, size, timestamp)
- upload serializer and view
- file validation helpers (type allowlist `.pdf`/`.txt`/`.md`, max 10 MB)
- triggers ingestion by dispatching the Celery task and creating the
  `IngestionJob`

### `apps/rag`

- `IngestionJob` tracking model
- the ingestion Celery task
- the ingestion pipeline (load -> split -> embed -> Chroma upsert)
- the ingestion status endpoint (internal-to-public status mapping)
- the chat query view and the retrieval + LLM chain
- optional `Conversation`/`Message` models for chat continuation
- the OpenRouter client wrapper and the local embedding wrapper boundaries

### `apps/common`

- shared enums (status vocabulary)
- shared exceptions
- the structured JSON logging helper / formatter
- the single `{"error": "<message>"}` response helper
- utility helpers used across apps

## Layering Within An App

Keep a consistent vertical layering so each slice is easy to review:

- `serializers.py` — request/response validation and shaping
- `views.py` — thin DRF views: authenticate, validate, delegate, respond
- `services.py` — business logic (ingestion orchestration, retrieval, credit
  accounting, ownership checks)
- `tasks.py` — Celery task entry points (thin wrappers over services)
- flat modules in `apps/rag`: `pipeline.py`, `retrieval.py`, `embeddings.py`,
  `llm.py`, `vectorstore.py`, `conversations.py` (no `pipeline/` package)
- `models.py` — persistence and model helper methods

Views must not contain pipeline logic; tasks must not contain HTTP concerns.
The OpenRouter call and the embedding model live behind service-layer wrappers
so they can be stubbed in `settings/test.py`.

## Configuration Strategy

### `config/settings/base.py`

- common Django, DRF, SimpleJWT, Celery, logging, storage, Chroma, embedding,
  and OpenRouter configuration read from environment

### `config/settings/local.py`

- local Docker-oriented defaults

### `config/settings/test.py`

- `CELERY_TASK_ALWAYS_EAGER = True` for synchronous task execution
- stubbed embedding model and stubbed OpenRouter client
- a temporary/isolated Chroma location
- test-only fast defaults

### `config/settings/production.py`

- env-only configuration (no insecure defaults)
- the settings module used by the Docker `web` and `celery` services
  (`DJANGO_SETTINGS_MODULE=config.settings.production`)

The settings split is base / local / test / production (4 modules).

### `config/celery.py`

- Celery app definition, broker/result backend wiring, autodiscovery of
  `apps/*/tasks.py`

## URL Strategy

- central route registration in `config/urls.py`
- each app owns its sub-routes
- endpoint paths match the assessment verbatim:
  `/api/register/`, `/api/login/`, `/api/documents/upload/`,
  `/api/documents/status/`, `/api/chat/query/`
- `api_contract.yaml` is the source of truth for the exact shapes

## Testing Layout

All tests live under the top-level `tests/` tree; there are no app-local test modules.

- `tests/unit/` — unit tests (serializers, validators, model helpers, status mapping)
- `tests/integration/` — multi-component API and async ingestion scenarios
- `tests/smoke/` — Docker and observability verification helpers

Test fixtures are generated programmatically inside the tests (deterministic small in-memory
`.txt`/`.md` content, an in-memory minimal PDF, and a deliberately corrupt byte payload for
failure propagation). There is no `tests/fixtures/` directory of version-controlled fixture files.

## Why This Structure

- enough separation for auth, upload, ingestion, retrieval, and chat concerns
- avoids over-splitting into too many apps (three product apps plus common)
- isolates external dependencies (LLM, embeddings, Chroma) behind service
  wrappers for offline testing
- keeps infrastructure configuration visible and easy to review
- supports every required service without enterprise-style layering
