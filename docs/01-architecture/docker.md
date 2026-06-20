# Docker And Compose Design

## Objective

Define the container topology and runtime expectations for the local R.A.V.I.D.
assessment stack so a reviewer can boot everything with a single Docker Compose
command.

Canonical non-infrastructure decisions live in
`.agents/references/assessment-decisions.md`.

## Services

### web

- Django API service (DRF + SimpleJWT)
- exposes the application HTTP port `8000`
- loads the local embedding model in-process for query embedding
- depends on healthy `db`, `redis`, and `chroma`

### db

- PostgreSQL service (`postgres:16-alpine`)
- system of record for relational data

### redis

- Celery broker and result backend

### celery

- Celery worker running the ingestion pipeline
  (load -> split -> embed -> Chroma upsert)
- loads the local embedding model in-process
- depends on healthy `db`, `redis`, and `chroma`

### chroma

- Chroma vector store service
- persists per-user collections (`user_{user_id}`) on a named volume

### loki

- stores structured logs for Grafana queries

### alloy

- Grafana Alloy; scrapes container logs and forwards them to Loki

### grafana

- dashboards and live log exploration UI
- depends on `loki`

## Exposed Ports

Recommended local defaults. Infra services bind to loopback only so they do not
collide with the application or leak to the network.

- web: `8000` (the application port)
- grafana: `3000`
- chroma: `127.0.0.1:8001:8000` — Chroma listens on `8000` inside its
  container; it is published on host `8001` to avoid clashing with `web:8000`.
  Loopback-bound so it is reachable for debugging but not exposed externally.
- postgres: `127.0.0.1:5432:5432` (loopback only, reviewer convenience; host port
  overridable via `POSTGRES_PUBLISHED_PORT`)
- redis: `127.0.0.1:6379:6379` (loopback only, reviewer convenience; host port
  overridable via `REDIS_PUBLISHED_PORT`)
- loki: `127.0.0.1:3100:3100` (loopback only; queried by Grafana within the compose
  network, also reachable from host for debugging)

## Startup Ordering

Use healthcheck-gated `depends_on` (`condition: service_healthy`):

- `web` depends on `db`, `redis`, and `chroma` being healthy
- `celery` depends on `db`, `redis`, and `chroma` being healthy
- `grafana` depends on `loki` being available

Provide healthchecks for `db` (e.g. `pg_isready`), `redis` (`redis-cli ping`),
and `chroma` (its heartbeat/v1 endpoint).

## Volume Strategy

Named Docker volumes for mutable service data:

- `pg_data` — PostgreSQL data
- `media` — application file storage (`uploads/user_{user_id}/`), mounted into
  both `web` and `celery` so the worker can read what `web` stored
- `chroma_data` — Chroma persistence
- `loki_data` — Loki log storage
- `grafana_data` — Grafana state/dashboards-db

Read-only bind mounts from the repo:

- Grafana provisioning files
- Alloy and Loki configuration

Do not store uploaded files or embeddings inside the database; they live on the
`media` and `chroma_data` volumes respectively.

## Environment Variable Strategy

Use `.env` for local runtime configuration. Do not use Docker build args for
runtime secrets.

## Required Environment Variables

Django / DRF:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_SETTINGS_MODULE`

Database:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

Redis / Celery:

- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

Chroma:

- `CHROMA_HOST`
- `CHROMA_PORT`

Embeddings (local HuggingFace, no key):

- `EMBEDDING_MODEL_NAME` (default `all-MiniLM-L6-v2`)

OpenRouter (LLM gateway):

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`)
- `OPENROUTER_MODEL` (a free-tier slug; verify at implementation time, slugs
  rotate)

Grafana:

- `GF_SECURITY_ADMIN_PASSWORD`

Provide every value in `.env.example` so reviewers can bootstrap the stack
without guessing variable names. `.env.example` must NOT contain a real
`OPENROUTER_API_KEY`; use a placeholder.

## Container Design Principles

- keep the stack minimal but complete (web, db, redis, celery, chroma, loki,
  alloy, grafana)
- keep reviewer startup commands short
- prefer named volumes over bind mounts for mutable service data
- bind infra ports to loopback to avoid clashes and exposure
- keep observable-behavior config (Alloy, Loki, Grafana provisioning)
  version-controlled
- never bake secrets into images

## Reviewer Workflow Goal

The reviewer should be able to:

1. copy `.env.example` to `.env` and set an OpenRouter key
2. run Docker Compose
3. wait for healthy core services
4. call the API
5. open Grafana and inspect Django and Celery logs without manual setup
