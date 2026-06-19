# RAVID

RAVID is a Retrieval-Augmented Generation (RAG) document chatbot backend: authenticated users upload documents (`.pdf`, `.txt`, `.md`), those documents are asynchronously parsed, chunked, embedded, and indexed into a per-user vector store, and users can then chat against *their own* documents and receive grounded answers with the LLM token cost metered against a per-user credit balance.

> **Status: foundation branch — scaffolding & specs only, no product code yet.**
> This branch (`feature/00-foundation-branch-pr-workflow`) ships the `.agents/` operating system, the `openspec/` configuration, and the `docs/` anchor/architecture material. There is **no Django, Celery, or product code in this branch** — application slices land on their own feature branches (01..08) per the roadmap below.

## Tech Stack (locked)

| Layer | Choice |
| --- | --- |
| Web framework | Django 5.x + Django REST Framework |
| Auth | `djangorestframework-simplejwt` (email + password → JWT) |
| Async | Celery workers, Redis broker + result backend |
| Relational store | PostgreSQL (documents, ingestion jobs, credit balances — source of truth) |
| Vector store | Chroma, one collection per user (`user_{user_id}`) |
| RAG toolkit | LangChain (document loaders + `RecursiveCharacterTextSplitter` + retriever) |
| Embeddings | Local HuggingFace `all-MiniLM-L6-v2` (384 dims, free, offline, no key) |
| LLM gateway | OpenRouter (OpenAI-compatible `chat/completions`), model `mistralai/mistral-7b-instruct:free` |
| Observability | Structured JSON logs → Grafana Alloy → Loki → Grafana |
| Delivery | Docker Compose |

Canonical, non-negotiable parameter values live in
[`.agents/references/assessment-decisions.md`](.agents/references/assessment-decisions.md).
The summary: chunk size `1000` / overlap `150`; retrieval `top_k=4`, cosine similarity;
uploads capped at `10 MB`; `tokens_consumed` is always read from the OpenRouter `usage`
field, never estimated.

## Per-User Isolation (read this first)

Isolation is the single most important invariant in RAVID and is enforced at every layer:

- **Vectors:** every user gets exactly one Chroma collection named `user_{user_id}`. A chat query only ever retrieves from the authenticated owner's collection. No cross-user vector or chunk ever enters a prompt.
- **Ownership:** documents, ingestion jobs, and vectors are scoped by an owner foreign key. Any attempt to access another user's resource returns **HTTP 404 — not 403** — so the API never leaks the existence of resources you do not own.
- **Auth:** a missing or invalid JWT returns **HTTP 401**.
- **Errors:** every error response uses a single-field envelope `{"error": "<message>"}`.

## API Surface (planned)

All paths keep trailing slashes. Protected routes require `Authorization: Bearer <jwt>`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/register/` | public | Create account `{email,password}` → `201 {message,user_id}` |
| `POST` | `/api/login/` | public | Obtain JWT `{email,password}` → `200 {message,token}` |
| `POST` | `/api/documents/upload/` | JWT | Upload one file (multipart, field `file`) → `202 {message,document_id,task_id}` |
| `GET` | `/api/documents/status/?task_id=<id>` | JWT | Ingestion status → `{task_id,status:PROCESSING\|SUCCESS\|FAILURE,...}` |
| `POST` | `/api/chat/query/` | JWT | Ask `{query}` → `200 {answer,tokens_consumed}` |
| `POST` | `/api/chat/query/` (bonus) | JWT | Multi-turn via `chat_id`; optional SSE streaming |

The machine-readable contract will live at
[`docs/01-architecture/api_contract.yaml`](docs/01-architecture/api_contract.yaml).

## Planned Architecture

```
                         ┌──────────────────────────────────────────┐
   Client (curl/Postman) │                  Django + DRF (web)        │
        │   JWT           │  /api/register  /api/login                 │
        ▼                 │  /api/documents/upload   (saves file,     │
  ┌───────────┐           │                           creates row,    │
  │  HTTP API │──────────▶│                           dispatches task)│
  └───────────┘           │  /api/documents/status   (reads DB row)   │
                          │  /api/chat/query         (retrieve+LLM)   │
                          └───────┬───────────────┬──────────────┬────┘
                                  │               │              │
                     enqueue task │        read   │ owner-scoped │ chat/completions
                                  ▼               ▼              ▼
                          ┌──────────────┐  ┌───────────┐  ┌──────────────┐
                          │ Redis broker │  │ PostgreSQL│  │  OpenRouter  │
                          └──────┬───────┘  │  (source  │  │  (LLM, usage │
                                 │          │ of truth) │  │  → tokens)   │
                                 ▼          └─────┬─────┘  └──────────────┘
                          ┌──────────────┐        │
                          │ Celery worker│        │ updates IngestionJob status
                          │  load → split │◀──────┘
                          │  → embed → upsert
                          └──────┬───────┘
                                 │ per-user collection user_{user_id}
                                 ▼
                          ┌──────────────┐     embeddings: local HF
                          │   Chroma     │◀──── all-MiniLM-L6-v2 (384d)
                          └──────────────┘

  Every service emits structured JSON logs ──▶ Grafana Alloy ──▶ Loki ──▶ Grafana
```

Ingestion pipeline (Celery): **load** (LangChain loader by file type) → **split**
(`RecursiveCharacterTextSplitter`, 1000/150) → **embed** (local HuggingFace) → **upsert**
(Chroma `user_{user_id}`). The PostgreSQL `IngestionJob` row is the source of truth for
status; the public `PROCESSING|SUCCESS|FAILURE` values are mapped from internal Celery
states. Parse/embed failures surface in **both** the logs and the task status — never
swallowed.

Chat query (request path): authenticate → retrieve `top_k=4` owner-scoped chunks
(cosine) → if nothing relevant, answer that there isn't enough information in the user's
documents → otherwise build a bounded prompt and call OpenRouter → read `usage` for
`tokens_consumed` → decrement the user's credit balance.

## Branch Roadmap

Each slice is one feature branch and one PR into merge-only `main`.

| Branch | Scope |
| --- | --- |
| `feature/00-foundation-branch-pr-workflow` | `.agents/` operating system, `openspec/` config, `docs/` anchors & architecture (**this branch**) |
| `feature/01-foundation-django-langchain-bootstrap` | Django + DRF + Celery + LangChain project skeleton, settings, base config |
| `feature/02-authentication-register-login-jwt` | `register` / `login`, JWT issuance & verification |
| `feature/03-document-upload-pdf-txt-md` | Upload endpoint, file-type/size validation, `Document` model, task dispatch |
| `feature/04-ingestion-pipeline-chunk-embed-chroma` | Celery ingestion: load → split → embed → Chroma upsert, status mapping |
| `feature/05-rag-chat-query-openrouter` | Retrieval + OpenRouter call, no-context guard, token metering, credit decrement |
| `feature/07-docker-and-delivery-compose-ci` | Docker Compose stack (web/worker/db/redis/chroma/alloy/loki/grafana), CI |
| `feature/08-bonus-chat-continuation-sse` | Bonus: multi-turn chat via `chat_id`, SSE streaming |

## Hybrid OpenSpec Workflow

RAVID combines the OpenSpec CLI with a branch/PR delivery discipline. The two systems own
different artifacts and do not duplicate each other:

1. **Specify (OpenSpec).** Each feature slice is an OpenSpec *change* under
   `openspec/changes/<NN-name>/` with `proposal.md`, `design.md`, and `tasks.md`,
   authored via `/opsx:propose`. These supersede the older `spec.md` / `plan.md`
   content — reference them rather than re-writing requirements.
2. **Branch.** Create `feature/NN-<scope>` for the slice.
3. **Implement (OpenSpec).** Build against the change via `/opsx:apply`, working through
   `tasks.md`.
4. **Deliver (docs/02-features).** Per-feature QA and delivery artifacts live under
   `docs/02-features/<NN-name>/`: `test_matrix.md`, `pr-review.md`,
   `validation-report.md`, `pull_request.md`.
5. **Review → mistake loop.** A review never closes without updating
   [`.agents/MISTAKE.md`](.agents/MISTAKE.md); recurring failures become guarded rules.
6. **Merge.** Open the PR into `main` (merge-only). Then `/opsx:archive` the change.

In short: **OpenSpec owns proposal/design/tasks; `docs/02-features/` owns
QA/review/validation/PR artifacts.** Project context for OpenSpec lives in
[`openspec/config.yaml`](openspec/config.yaml). The full 7-phase pipeline, Phase 0
session-resume, locked-decisions discipline, and source-of-truth precedence are described
in [`.agents/WORKFLOW.md`](.agents/WORKFLOW.md) and [`.agents/AGENTS.md`](.agents/AGENTS.md).

## Repository Layout (foundation)

```
.agents/        operating system for agents (guidelines, references, templates, skills, scripts)
openspec/       OpenSpec config + specs/ + changes/ (per-feature proposal/design/tasks)
docs/00-anchor/        brd / srs / glossary / task
docs/01-architecture/  system_context / project_structure / database / docker / observability / testing + api_contract.yaml
docs/02-features/      per-slice delivery artifacts (added as slices land)
README.md  .gitignore  .env.example  AGENTS.md
```

## Setup & Run

> Docker Compose instructions and the full reviewer run path arrive in **slice 07**
> (`feature/07-docker-and-delivery-compose-ci`). There is no runnable application in the
> foundation branch yet.

When the stack lands, the reviewer path will be:

```bash
cp .env.example .env   # fill in OPENROUTER_API_KEY, leave the rest as sensible defaults
docker compose up --build -d
```

API will be served on `http://localhost:8000` and Grafana on `http://localhost:3000`.
The first run downloads the local embedding model (`all-MiniLM-L6-v2`) into a cached
volume; OpenRouter is the only service that requires an API key.

## License

Take-home assessment deliverable; not for redistribution.
