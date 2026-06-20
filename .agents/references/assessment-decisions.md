# Assessment Decisions

This is **the canonical locked-decisions register** for the RAVID backend assessment. Every
decision below is **locked** for this repo unless the user explicitly overrides it. Each entry is
numbered, dated, and carries a one-line rationale.

When any other artifact (openspec proposal/design/tasks, docs, skills, templates, code) needs a
default, it cites the decision id here (e.g. `[D-007]`) rather than re-deciding. If a decision is
ever changed, update it here first, bump the date, and log the change in
`.agents/MISTAKE.md` if the change was forced by a discovered error.

> Source-of-truth precedence: assessment PDF brief > this register > openspec change artifacts >
> docs/ > code. Where the brief is silent or ambiguous, the chosen default lives here and is
> flagged as a decision (not a fact).

---

## Stack (locked)

### D-001 — Language & framework — 2026-06-18
Python 3.12, Django 5.x + Django REST Framework. **Rationale:** brief mandates a Django/DRF
backend; 3.12 is the current stable interpreter matching Django 5.x support.

### D-002 — Auth mechanism — 2026-06-18
`djangorestframework-simplejwt` for JWT issuance/verification on protected routes.
**Rationale:** brief requires JWT-protected APIs; simplejwt is the DRF-standard package.

### D-003 — Async processing — 2026-06-18
Celery 5.x with **Redis** as both broker and result backend. **Rationale:** ingestion (parse →
chunk → embed → upsert) is heavy and must not block the request/response cycle; Redis is the
simplest single-dependency broker+backend for a time-boxed delivery.

### D-004 — Relational store — 2026-06-18
PostgreSQL for users, documents, ingestion jobs, chat sessions/messages, and credit balances.
**Rationale:** durable relational metadata + the **DB row is the source of truth** for task status
(see D-019).

### D-005 — Vector store — 2026-06-18
**Chroma** as the vector store. **Rationale:** brief names a RAG document chatbot; Chroma is a
lightweight, self-hostable vector DB that runs in Docker Compose alongside the stack.

### D-006 — RAG orchestration — 2026-06-18
**LangChain** for document loaders, `RecursiveCharacterTextSplitter`, and the retriever interface.
**Rationale:** standard, well-documented building blocks; keeps loader/splitter/retriever swappable
without bespoke code.

---

## LLM & Embeddings (locked)

### D-007 — LLM gateway: OpenRouter — 2026-06-18
LLM calls go through **OpenRouter**, base URL **`https://openrouter.ai/api/v1`**, using the
**OpenAI-compatible** `chat/completions` request/response shape (NOT the Anthropic Messages API).
**Rationale:** OpenRouter is an OpenAI-compatible gateway; using its OpenAI shape lets us use the
`openai`/LangChain OpenAI client unchanged. **Do not** answer provider/model API-shape questions
from memory — verify (see D-009, M-009).

### D-008 — LLM model slug — 2026-06-18
Default model slug **`google/gemma-4-31b-it:free`**. **Rationale:** free tier keeps the
assessment zero-cost. **Caveat:** OpenRouter free slugs rotate/deprecate — **verify the slug is
still live at implementation time** and update this entry if it changed.

### D-009 — Token accounting from response `usage` — 2026-06-18
`tokens_consumed` is read from the **`usage`** field of the OpenRouter chat/completions response;
**never estimate or count tokens locally.** **Rationale:** the response is authoritative; estimates
drift and would corrupt credit accounting (D-016).

### D-010 — Embeddings: local HuggingFace — 2026-06-18
Embeddings use **local HuggingFace `all-MiniLM-L6-v2`** (**384 dims**) via `langchain-huggingface`
(sentence-transformers under the hood). **Rationale:** OpenRouter's free tier has **no embeddings
endpoint**; this model is free, runs **offline with no API key**, and 384-dim vectors are cheap to
store/search. Chroma collections are created with this dimensionality; changing the model requires
re-embedding all documents.

---

## RAG Pipeline (locked)

### D-011 — Chunking parameters — 2026-06-18
`RecursiveCharacterTextSplitter` with **`chunk_size=1000`**, **`chunk_overlap=150`**.
**Rationale:** ~1000-char chunks balance retrieval granularity vs. context size; 150 overlap
preserves cross-boundary meaning. Mirror these exact values in code and tests.

### D-012 — Retrieval parameters — 2026-06-18
Retrieval uses **`top_k=4`** with **cosine** similarity. **Rationale:** 4 chunks is enough context
for a 7B model without overflowing the prompt (see D-014); cosine matches all-MiniLM-L6-v2's
normalized embedding space.

### D-013 — Per-user vector isolation — 2026-06-18
**One Chroma collection per user**, named **`user_{user_id}`**. Every retrieval/query is scoped to
the authenticated owner's collection only. **Rationale:** hard isolation boundary so one user can
never retrieve another user's chunks; per-collection scoping is simpler and safer than per-document
metadata filtering. Cross-user access is a top mistake to guard (M-005).

### D-014 — Bounded LLM context — 2026-06-18
Only the **`top_k` (=4) retrieved chunks** are sent to the LLM as context — never the full document
or an unbounded chunk set. **Rationale:** bounds prompt size, cost, and latency; unbounded context
is a logged mistake (M-007).

### D-015 — No-relevant-context guard — 2026-06-18
If retrieval returns nothing relevant for a query, the chat answer states there **is not enough
information in the user's documents** to answer, rather than hallucinating. **Rationale:** RAG
quality requires refusing to fabricate when grounding is absent.

---

## Credit / Subscription (locked)

### D-016 — Per-user credit balance — 2026-06-18
Maintain a simple **per-user credit balance** in Postgres, **decremented by `tokens_consumed`**
(D-009) on each chat query. **Rationale:** brief's "Subscription Management" / "Credit Consumption"
implies tracking usage; tying deduction to the authoritative `usage` figure keeps balances exact.
(Exact reject-on-zero / starting-balance policy is decided in the chat slice's openspec change;
default starting balance and behavior on insufficient credit must be documented there before coding.)

---

## API & HTTP Contract (locked)

> Endpoints below are **verbatim from the assessment PDF**. Earlier drafts guessed wrong paths;
> these are authoritative.

### D-017 — Endpoint surface — 2026-06-18
| Method | Path | Auth | Body | Success | Error |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/register/` | none | JSON `{email, password}` | `201 {message, user_id}` | `400 {error}` |
| POST | `/api/login/` | none | JSON `{email, password}` | `200 {message, token}` | `401 {error}` |
| POST | `/api/documents/upload/` | JWT | multipart, field `file` | `202 {message, document_id, task_id}` | `400 {error}` |
| GET | `/api/documents/status/?task_id=<id>` | JWT | — | `200 {task_id, status, ...}` | `404 {error}` |
| POST | `/api/chat/query/` | JWT | JSON `{query}` | `200 {answer, tokens_consumed}` | `400/401 {error}` |
| POST | `/api/chat/query/` (bonus) | JWT | JSON `{query, chat_id?}` + SSE | `200` streamed | — |

**Rationale:** matches the brief exactly so reviewers' smoke tests pass against expected paths.

### D-018 — Upload constraints — 2026-06-18
Uploads accept only **`.pdf`, `.txt`, `.md`**, **max 10 MB**. Any other type/oversize is rejected
with **`HTTP 400 {"error": "..."}"`** before any async work is queued. **Rationale:** bounds parse
surface and protects the worker; reject early and cheaply.

### D-019 — Task status: DB row is source of truth — 2026-06-18
`/api/documents/status/` returns the **public** status derived from the DB ingestion-job row, not
raw Celery state. Public statuses: **`PROCESSING`**, **`SUCCESS`**, **`FAILURE`**. Internal Celery
states map to these (e.g. internal `STARTED`/`PENDING`/`RETRY` → public `PROCESSING`). **Rationale:**
the DB row survives broker restarts and gives a stable, ownership-checked contract; carried over from
the reference repo's internal-vs-public mapping discipline.

### D-020 — Ownership returns 404, not 403 — 2026-06-18
Every document, ingestion job, status lookup, and vector query is scoped by an **owner FK**.
Cross-user access to a resource that exists but isn't yours returns **`404 Not Found`** (NOT 403),
to avoid leaking existence. **Rationale:** 403 confirms the resource exists; 404 does not. Carried
over verbatim from the reference repo.

### D-021 — Auth failures return 401 — 2026-06-18
Missing or invalid JWT on a protected route returns **`HTTP 401`** with `{"error": "..."}`.
**Rationale:** distinguishes "not authenticated" (401) from "authenticated but not yours" (404 per
D-020).

### D-022 — Error envelope — 2026-06-18
**Every** error response uses the single-field envelope **`{"error": "<message>"}`** (one string
field, no nested DRF default shapes). **Rationale:** uniform client handling; matches the brief's
example responses.

### D-023 — `confirm_password` handling — 2026-06-18
The brief's register example shows **only `{email, password}`**. Decision: **do not require
`confirm_password`.** Registration validates `email` + `password` only. **Rationale:** match the
brief's documented request shape exactly. If a `confirm_password` field is sent, it is ignored
rather than rejected (lenient). This deviates from the reference repo (which supported
`confirm_password`); the deviation is intentional because the RAVID brief omits it. Revisit in the
auth slice's openspec change if the PDF body contradicts the example.

---

## Workflow & Architecture (locked)

### D-024 — Hybrid OpenSpec + branch/PR workflow — 2026-06-18
Each feature slice is **both** an OpenSpec change **and** a git branch + PR:
- **OpenSpec owns** the proposal/design/tasks: `openspec/changes/<NN-name>/{proposal.md,
  design.md, tasks.md}`, authored via `/opsx:propose`, implemented via `/opsx:apply`, archived via
  `/opsx:archive`.
- **`docs/02-features/<NN-name>/` owns** the delivery/QA artifacts: `test_matrix.md`,
  `pr-review.md`, `validation-report.md`, `pull_request.md`.
- One git branch `feature/NN-<scope>` per slice, one PR into **merge-only `main`**.
- `spec.md`/`plan.md` content is **superseded** by openspec `proposal.md`/`design.md`/`tasks.md`;
  templates reference openspec rather than duplicating it.

**Rationale:** keeps the reference repo's branch/PR + delivery-artifact discipline while delegating
spec/design/tasks authoring to the installed OpenSpec CLI (spec-driven schema). Avoids duplicate,
drifting spec files.

### D-025 — Async ingestion vs. synchronous chat — 2026-06-18
Document **ingestion** (parse → chunk → embed → upsert) runs **asynchronously in Celery** and is
polled via `/api/documents/status/`. The **chat query** runs **synchronously** within the
`/api/chat/query/` request (retrieve → call LLM → return answer). **Rationale:** ingestion is heavy
and latency-tolerant (upload returns `202` + `task_id`); chat must return an answer in the same
request to satisfy the `200 {answer, tokens_consumed}` contract. The bonus SSE path (D-017) streams
the synchronous chat response.

### D-026 — Failures surface in logs AND task status — 2026-06-18
Embedding/parse/upsert failures during ingestion must be **surfaced in both** structured logs and
the `/api/documents/status/` response (public `FAILURE` + an error message), never swallowed.
**Rationale:** a silently failed ingestion looks "done" to the user and corrupts retrieval; this is
mistake M-006.

### D-027 — Secrets and raw document text never logged — 2026-06-18
Structured logs **must not** contain the OpenRouter API key, embedding keys/paths that leak
secrets, or **raw uploaded document text / chunk contents**. Log identifiers, counts, durations,
statuses — not payloads. **Rationale:** privacy + secret hygiene; this is mistake M-008.

---

## Storage & Processing (locked)

### D-028 — Uploaded file storage — 2026-06-18
Uploaded documents are stored in **application-managed file storage** (local volume in Docker for
the assessment), with **metadata + task linkage persisted in Postgres**. **Rationale:** keeps the
binary out of the DB while the DB remains the authoritative index/owner record.

---

## Observability (locked)

### D-029 — Structured JSON logs → Alloy → Loki → Grafana — 2026-06-18
Django and Celery both emit **structured JSON logs**, shipped by **Grafana Alloy** (not Promtail) to
**Loki**, visualized in **Grafana**. Service labels: `service=web` (web API), `service=celery`
(worker). Keep Loki labels low-cardinality (`service`, `container`, `job`); high-cardinality fields
(`task_id`, `document_id`, `owner_id`) stay in the JSON payload only. **Rationale:** Promtail is
EOL; low-cardinality labels keep Loki performant; matches the reference repo's observability
discipline adapted to RAG identifiers.

---

## Delivery (locked)

### D-030 — Per-feature delivery workspaces — 2026-06-18
Maintain one delivery workspace per slice under `docs/02-features/`, named to match the openspec
change and feature branch:
- `01-foundation-django-langchain-bootstrap/`
- `02-authentication-register-login-jwt/`
- `03-document-upload-pdf-txt-md/`
- `04-ingestion-pipeline-chunk-embed-chroma/`
- `05-rag-chat-query-openrouter/`
- `07-docker-and-delivery-compose-ci/`
- `08-bonus-chat-continuation-sse/`

Do not postpone README, API docs, or dashboard provisioning to the end (mistake M-004).
**Rationale:** delivery artifacts authored alongside each slice stay accurate and reviewable.

---

## Cross-references

- Validation commands that exercise these decisions: `.agents/references/assessment-validation.md`
- Final go/no-go gate: `.agents/references/submission-checklist.md`
- Official docs backing the stack/LLM choices: `.agents/references/source-links.md`
- Mistake guards (M-001…M-009): `.agents/MISTAKE.md`
- Branch roadmap & 7-phase pipeline: `.agents/WORKFLOW.md`
