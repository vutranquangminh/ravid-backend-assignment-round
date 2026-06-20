# RAVID — RAG Document Chatbot Backend

[![CI](https://github.com/vutranquangminh/ravid-backend-assignment-round/actions/workflows/pr-ci.yml/badge.svg)](https://github.com/vutranquangminh/ravid-backend-assignment-round/actions/workflows/pr-ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/Django-5.x-092E20)
![Tests](https://img.shields.io/badge/tests-754%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

RAVID is a Retrieval-Augmented Generation (RAG) document chatbot backend. Authenticated users upload documents (`.pdf`, `.txt`, `.md`), those documents are asynchronously parsed, chunked, embedded, and indexed into a per-user vector store. Users can then chat against **their own documents** and receive grounded answers — with LLM token cost metered against a per-user credit balance.

## Tech Stack (locked)

| Layer | Choice |
|---|---|
| Web framework | Django 5.x + Django REST Framework |
| Auth | `djangorestframework-simplejwt` (email + password → JWT) |
| Async | Celery workers, Redis broker + result backend |
| Relational store | PostgreSQL (documents, ingestion jobs, credit balances) |
| Vector store | Chroma `1.5.9`, one collection per user (`user_{user_id}`) |
| RAG toolkit | LangChain `RecursiveCharacterTextSplitter` (chunking) + `HuggingFaceEmbeddings`; the Chroma client handles per-user indexing & retrieval directly — see note below |
| Embeddings | Local HuggingFace `all-MiniLM-L6-v2` (384 dims, free, offline) |
| LLM gateway | OpenRouter (`google/gemma-4-31b-it:free`) |
| API docs | drf-spectacular → Swagger UI at `/api/docs/` |
| Observability | Structured JSON logs → Grafana Alloy → Loki → Grafana |
| Delivery | Docker Compose (8 services) |

Canonical, non-negotiable parameter values live in [`.agents/references/assessment-decisions.md`](.agents/references/assessment-decisions.md): chunk size `1000` / overlap `150`; retrieval `top_k=4`, cosine similarity; uploads capped at `10 MB`; `tokens_consumed` is always read from the OpenRouter `usage` field, never estimated.

> **Note on LangChain usage.** LangChain provides the **chunking** (`RecursiveCharacterTextSplitter`) and the **embeddings** abstraction (`langchain-huggingface`). For the vector store and retrieval we call the **`chromadb` client directly** (not `langchain_chroma`) — a deliberate choice: it keeps strict control over the per-user collection scoping (`user_{id}`) that underpins our isolation guarantee, and avoids coupling to the fast-moving `langchain` 1.x vector-store API. Text extraction uses `pypdf` for PDFs and UTF‑8 reads for TXT/MD. The retrieval flow (`embed query → query the caller's collection → build bounded context → LLM`) is the standard RAG pipeline, implemented explicitly.

## Per-User Isolation

Isolation is the single most important invariant:

- **Vectors:** every user gets exactly one Chroma collection `user_{user_id}`. A chat query only ever retrieves from the authenticated owner's collection.
- **Ownership:** documents, ingestion jobs, and vectors are scoped by owner foreign key. Accessing another user's resource returns **HTTP 404** — never 403.
- **Auth:** missing or invalid JWT returns **HTTP 401**.
- **Errors:** every error response uses `{"error": "<message>"}`.

## Architecture

```
   Client (curl / Postman / Swagger UI)
        │  JWT
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │                Django + DRF  (web, port 8000)           │
  │  /api/register   /api/login                             │
  │  /api/documents/upload   → saves file, creates row,    │
  │                             dispatches Celery task      │
  │  /api/documents/status   → reads IngestionJob row      │
  │  /api/chat/query         → retrieve + LLM              │
  │  /api/schema/            → OpenAPI spec (AllowAny)     │
  │  /api/docs/              → Swagger UI (AllowAny)       │
  └──────────────┬──────────────────┬──────────────────────┘
                 │                  │
     enqueue     │    read/write    │   owner-scoped
     Celery task │    PostgreSQL    │   chat/completions
                 ▼                  ▼
        ┌──────────────┐    ┌──────────────────┐
        │ Redis broker │    │   OpenRouter LLM │
        └──────┬───────┘    └──────────────────┘
               ▼
        ┌──────────────────────────────────────┐
        │  Celery worker                       │
        │  load → split → embed → upsert       │
        └──────────────┬───────────────────────┘
                       │ user_{user_id} collection
                       ▼
                ┌──────────────┐
                │    Chroma    │ ← HuggingFace all-MiniLM-L6-v2
                └──────────────┘

  All services emit JSON logs ──▶ Alloy ──▶ Loki ──▶ Grafana (port 3000)
```

## Running with Docker Compose (Reviewer Path)

**Prerequisites:** Docker + Docker Compose, an [OpenRouter](https://openrouter.ai/) API key.

```bash
# 1. Copy the env template and fill in your OpenRouter key
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY=sk-or-...

# 2. Build and start all 8 services
docker compose up --build

# 3. Wait ~60 s for the stack to be healthy, then try the API
curl http://localhost:8000/api/health/
# → {"status": "ok"}
```

| Service | URL |
|---|---|
| Django API | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/api/docs/` |
| OpenAPI schema | `http://localhost:8000/api/schema/` |
| Grafana | `http://localhost:3000` (admin / admin) |
| Chroma (internal) | `http://localhost:8001` |

> **First run note:** the Celery worker downloads `all-MiniLM-L6-v2` (~90 MB) on first ingestion. Subsequent runs use the Docker layer cache.

## API Walkthrough

```bash
BASE=http://localhost:8000

# Register
curl -s -X POST $BASE/api/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"reviewer@example.com","password":"Sup3rSecret!"}'

# Login (grab the token)
TOKEN=$(curl -s -X POST $BASE/api/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"reviewer@example.com","password":"Sup3rSecret!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Upload a document
curl -s -X POST $BASE/api/documents/upload/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/document.pdf"
# → {"message":"...", "document_id":1, "task_id":"<uuid>"}

# Poll ingestion status
curl -s "$BASE/api/documents/status/?task_id=<uuid>" \
  -H "Authorization: Bearer $TOKEN"
# → {"task_id":"<uuid>", "status":"SUCCESS", "message":"..."}

# Chat
curl -s -X POST $BASE/api/chat/query/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the main topic of this document?"}'
# → {"answer":"...", "tokens_consumed":42}
```

See [`docs/api/README.md`](docs/api/README.md) for the Postman collection import instructions.

## Local Development (no Docker)

```bash
# Create and activate a virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# Install all extras (RAG libs + dev tools)
pip install -e '.[rag,dev]'

# Apply migrations (uses sqlite by default in local settings)
python manage.py migrate

# Run the dev server
python manage.py runserver
```

## Running Tests

```bash
# Full suite (offline — no Docker, no network)
pytest -q

# With coverage
pytest --cov=apps --cov=config --cov-report=term-missing

# Lint
ruff check apps/ tests/ config/
```

The test suite uses `config.settings.test` (sqlite in-memory, Celery eager, stub embeddings + LLM). All 572+ tests run offline.

## Observability

Every Django and Celery log line is emitted as structured JSON on stdout. Fields:

| Field | Description |
|---|---|
| `ts` | ISO timestamp |
| `level` | log level |
| `logger` | logger name |
| `request_id` | per-request UUID |
| `user_id` | authenticated user pk |
| `document_id` | source document pk |
| `task_id` | Celery task id |
| `operation` | `upload` / `embed` / `retrieve` / `llm` |
| `duration_ms` | operation wall time |

Grafana Alloy collects stdout from Docker containers (via Docker socket), parses JSON, and promotes only `service` (`django` or `celery`) as a Loki label. Open Grafana at `http://localhost:3000` — the **R.A.V.I.D. Observability** dashboard is pre-provisioned.

## Slice / Branch Map

| Branch | Scope |
|---|---|
| `feature/00-foundation-branch-pr-workflow` | `.agents/` OS, `openspec/` config, `docs/` anchors |
| `feature/01-foundation-django-langchain-bootstrap` | Django + DRF + Celery + LangChain skeleton |
| `feature/02-authentication-register-login-jwt` | register / login, JWT |
| `feature/03-document-upload-pdf-txt-md` | Upload endpoint, Document model |
| `feature/04-ingestion-pipeline-chunk-embed-chroma` | Celery ingestion pipeline, Chroma upsert |
| `feature/05-rag-chat-query-openrouter` | Retrieval + LLM call, credit metering |
| `feature/07-docker-and-delivery-compose-ci` | Docker Compose, CI, API docs (this branch) |

## License

Take-home assessment deliverable; not for redistribution.
