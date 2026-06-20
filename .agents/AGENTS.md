# R.A.V.I.D. Assessment Agent Guide

This repository is optimized for one goal: deliver the RAVID RAG document chatbot backend assessment quickly without creating hidden quality debt that will slow the final submission.

RAVID = a Retrieval-Augmented Generation document chatbot backend. Users register, log in (JWT), upload documents (`.pdf`/`.txt`/`.md`), the documents are ingested asynchronously (LangChain load -> chunk -> embed -> Chroma upsert) into a per-user vector collection, and users then chat against their own documents (retrieval -> OpenRouter LLM -> answer + `tokens_consumed`).

## Mission

- Build a clean, submission-ready RAG backend covering authentication, document upload, asynchronous ingestion, per-user vector retrieval, LLM chat answering, observability, and Dockerized delivery.
- Optimize for fast, credible delivery, not for generic framework-building.
- Keep decisions explicit so the agent does not re-decide the same questions on every task.

## Read Order

Read these before substantial work:

1. `.agents/AGENTS.md`
2. `.agents/WORKFLOW.md`
3. `.agents/MISTAKE.md`
4. `docs/00-anchor/task.md`
5. `docs/00-anchor/srs.md`
6. `.agents/references/assessment-decisions.md`
7. The active OpenSpec change: `openspec/changes/<NN-name>/{proposal,design,tasks}.md` (list with `openspec list --json`)
8. The relevant skill in `.agents/skills/`
9. The active workstream artifacts in `docs/02-features/<NN-name>/`
10. `docs/00-anchor/brd.md`, `docs/00-anchor/srs.md`, and `docs/00-anchor/glossary.md` when the active task depends on requirements or terminology

The `/opsx:*` commands in `.claude/commands/opsx/` and the `openspec-*` skills in `.claude/skills/` are the mechanism for authoring and applying the OpenSpec change; consult them when running Phase 1, Phase 3, or Phase 6 of the workflow.

## Source Of Truth Order

When guidance conflicts, use this order:

1. `docs/00-anchor/srs.md`
2. `.agents/references/assessment-decisions.md`
3. `openspec/changes/<NN-name>/proposal.md` and `design.md` (the active feature contract)
4. `.agents/AGENTS.md`
5. `.agents/WORKFLOW.md`
6. Relevant `.agents/guidelines/*`
7. Existing code and docs in the repo

Note: `openspec/changes/<NN>/{proposal,design,tasks}.md` supersedes the older `spec.md`/`plan.md` template content. Reference the OpenSpec artifacts rather than duplicating their content into `docs/`.

## Session Resume Protocol

Before planning or coding in a fresh AI session, run this resume pass in order:

1. Check the current branch and `git status --short --branch`.
2. Read `docs/00-anchor/task.md`.
3. Inspect recent history with `git log --oneline --decorate --max-count=15`.
4. Read `docs/00-anchor/srs.md`.
5. Read `.agents/references/assessment-decisions.md`.
6. List active OpenSpec changes with `openspec list --json`; read the active change's `openspec/changes/<NN-name>/{proposal,design,tasks}.md`.
7. Read any non-empty workstream artifacts under:
   - `docs/02-features/01-foundation/`
   - `docs/02-features/02-authentication/`
   - `docs/02-features/03-document-upload/`
   - `docs/02-features/04-ingestion-pipeline/`
   - `docs/02-features/05-rag-chat-query/`
   - `docs/02-features/07-docker-and-delivery/`
   - `docs/02-features/08-bonus-chat-continuation-sse/`
8. If the active task depends on requirements or terminology, read:
   - `docs/00-anchor/brd.md`
   - `docs/00-anchor/srs.md`
   - `docs/00-anchor/glossary.md`

Resume rules:

- `docs/00-anchor/task.md` is the intended human snapshot.
- If `task.md` conflicts with branch state, git history, or `openspec/changes/`, report the mismatch and use repo truth for execution until the docs are updated.
- Treat empty files under `docs/02-features/` as missing progress signal and say so explicitly instead of inferring progress.
- A workstream is only complete when both its OpenSpec change is archived AND its `docs/02-features/<NN>/` artifacts exist.
- Map legacy/CSV branch aliases to numbered RAVID workstreams during resume:
  - `foundation` -> `01-foundation`
  - `authentication` -> `02-authentication`
  - `csv-upload` / `files` -> `03-document-upload`
  - `processing-pipeline` / `operations` -> `04-ingestion-pipeline`
  - `task-status` -> folded into `03-document-upload` / `04-ingestion-pipeline` status endpoint
  - `perform-operation` -> `05-rag-chat-query`
  - `observability` -> folded into `07-docker-and-delivery`
  - `docker-and-delivery` -> `07-docker-and-delivery`

Resume output must state:

- current branch
- resume sources checked
- current workstream and active OpenSpec change
- completed workstreams
- latest validated state
- next intended task
- open doc/repo/openspec conflicts

## Locked Stack Defaults

Use these defaults unless the user explicitly overrides them. The canonical, fully-specified values live in `.agents/references/assessment-decisions.md`.

- Python `3.12`
- Django `5.x`
- Django REST Framework
- `djangorestframework-simplejwt`
- Celery `5.x`
- Redis (Celery broker/result backend)
- PostgreSQL (relational source of truth)
- Chroma (vector store; one collection per user named `user_{user_id}`)
- LangChain (document loaders + `RecursiveCharacterTextSplitter` + retriever)
- OpenRouter (LLM gateway, OpenAI-compatible chat/completions shape)
- local HuggingFace embeddings `all-MiniLM-L6-v2` (384 dims) via `langchain-huggingface`
- Docker Compose
- Structured JSON logs -> Grafana Alloy -> Loki -> Grafana

## Locked Delivery Strategy

- Use one OpenSpec change AND one feature workspace per workstream:
  - OpenSpec change: `openspec/changes/<NN-name>/`
  - QA/review/validation/PR artifacts: `docs/02-features/<NN-name>/`
- Workstreams:
  - `01-foundation` (Django + LangChain bootstrap)
  - `02-authentication` (register / login / JWT)
  - `03-document-upload` (`.pdf`/`.txt`/`.md` upload + validation + status endpoint)
  - `04-ingestion-pipeline` (Celery: load -> chunk -> embed -> Chroma upsert)
  - `05-rag-chat-query` (retrieval -> OpenRouter -> answer + `tokens_consumed`)
  - `07-docker-and-delivery` (Docker Compose, observability, CI, README, API docs)
  - `08-bonus-chat-continuation-sse` (chat continuation via `chat_id`; SSE streaming)
- Deliver in vertical slices in this order:
  1. project foundation
  2. auth
  3. document upload
  4. ingestion pipeline
  5. RAG chat query
  6. docker and delivery (incl. observability)
  7. bonus: chat continuation + SSE
- Keep API documentation and README in scope from the start.

## Git Workflow

- `main` is merge-only for feature and product work.
- Changes limited to `AGENTS.md` and `.agents/**` may be committed directly to `main` when they are isolated from product changes (the `.agents`-direct-to-main exception).
- Every feature or workstream change must start from a new branch created from the latest `main`.
- Do not develop feature work directly on `main`.
- Every feature branch must open a pull request back into `main`.
- One OpenSpec change maps to one feature branch maps to one PR.
- Branch naming format:
  - `feature/<nn-workstream>-<short-scope>`
- Branch naming rules:
  - use lowercase letters only
  - use kebab-case for both workstream and scope
  - keep `<short-scope>` concise and implementation-specific
- Allowed workstream names align with `docs/02-features/` and `openspec/changes/`:
  - `00-foundation` (this branch: process/operating-system only)
  - `01-foundation`
  - `02-authentication`
  - `03-document-upload`
  - `04-ingestion-pipeline`
  - `05-rag-chat-query`
  - `07-docker-and-delivery`
  - `08-bonus-chat-continuation-sse`
- Branch roadmap:
  - `feature/00-foundation-branch-pr-workflow`
  - `feature/01-foundation-django-langchain-bootstrap`
  - `feature/02-authentication-register-login-jwt`
  - `feature/03-document-upload-pdf-txt-md`
  - `feature/04-ingestion-pipeline-chunk-embed-chroma`
  - `feature/05-rag-chat-query-openrouter`
  - `feature/07-docker-and-delivery-compose-ci`
  - `feature/08-bonus-chat-continuation-sse`
- Legacy/CSV aliases may still appear in existing branches and should be mapped during resume using the rules above.

## Locked Assessment Decisions

These defaults are already chosen for speed and consistency. The canonical, full list lives in `.agents/references/assessment-decisions.md`; the highlights:

- Endpoints (verbatim from the assessment PDF):
  - `POST /api/register/` (JSON `{email,password}`) -> `201 {message,user_id}` | `400 {error}`
  - `POST /api/login/` (JSON `{email,password}`) -> `200 {message,token}` | `401 {error}`
  - `POST /api/documents/upload/` (multipart `file`; JWT) -> `202 {message,document_id,task_id}` | `400 {error}`
  - `GET /api/documents/status/?task_id=<id>` (JWT) -> `{task_id,status:PROCESSING|SUCCESS|FAILURE,...}`
  - `POST /api/chat/query/` (JSON `{query}`; JWT) -> `200 {answer,tokens_consumed}`
  - Bonus: chat continuation via `chat_id`; SSE streaming.
- Uploads: allow `.pdf` `.txt` `.md` only, max 10 MB; reject others with `400 {error:"..."}`.
- Chunking: `RecursiveCharacterTextSplitter` `chunk_size=1000`, `chunk_overlap=150`.
- Retrieval: `top_k=4`, similarity = cosine.
- Embeddings: local HuggingFace `all-MiniLM-L6-v2` (384 dims) via `langchain-huggingface` (free, offline, no key; OpenRouter free tier has NO embeddings).
- LLM: OpenRouter base url `https://openrouter.ai/api/v1`, OpenAI-compatible chat/completions shape (NOT Anthropic Messages), model slug `google/gemma-4-31b-it:free` (free slugs rotate; verify at impl time). Read `tokens_consumed` from the response `usage` field, never estimate.
- Per-user vector isolation: ONE Chroma collection per user named `user_{user_id}`; every query scoped to the authenticated owner.
- Ownership/authz: cross-user access to a document/task/vector returns `404` (NOT 403, to avoid leaking existence); missing/invalid JWT -> `401`.
- No-relevant-context guard: if retrieval returns nothing relevant, answer that there isn't enough information in the user's documents.
- Credit/subscription: maintain a simple per-user credit balance, decremented by `tokens_consumed`.
- Error envelope everywhere: `{"error": "<message>"}` (single string field).
- Use Grafana Alloy instead of Promtail because the assessment allows either and Promtail is EOL.

Details belong in `.agents/references/assessment-decisions.md`. If the assessment brief is ambiguous, lock the default there before implementation proceeds.

## Definition Of Done

Work is not done until all relevant items are true:

- required endpoints are implemented and match the verbatim contract
- auth flow works (register, login, JWT-protected routes)
- document upload validates type/size and returns `202 {message,document_id,task_id}`
- Celery-backed ingestion works (load -> chunk -> embed -> Chroma upsert) into the per-user collection
- task status endpoint reflects `PROCESSING|SUCCESS|FAILURE` with failures surfaced (not swallowed)
- RAG chat returns grounded answers + real `tokens_consumed` from the `usage` field, with the no-context guard honored
- per-user vector isolation is enforced and cross-user access returns 404
- credit balance is decremented by `tokens_consumed`
- structured JSON logs are emitted (no secrets, no raw document text)
- logs are visible in Grafana via Alloy -> Loki
- Docker Compose boots the required services
- README contains setup and run instructions
- API docs exist
- the OpenSpec change is applied and archived
- validation is recorded under `docs/02-features/<NN>/validation-report.md`
- review is completed under `docs/02-features/<NN>/pr-review.md`
- `MISTAKE.md` has been checked and updated if needed

## Review Discipline

- Every substantial change must be reviewed.
- Every review must read `.agents/MISTAKE.md` first.
- Findings come before summary.
- Every review must state whether an active mistake rule was repeated, using exactly one of:
  - `No active mistake repeated.`
  - `Repeated mistake: M-XXX`
- New recurring failures must be written into `.agents/MISTAKE.md`.

## Skills In This Repo

Use the smallest relevant set under `.agents/skills/`:

- `agent-self-audit`
- `ravid-orchestrator`
- `django-api-delivery`
- `rag-ingestion-pipeline`
- `rag-chat-retrieval`
- `observability-compose-delivery`
- `review-mistake-guard`

The OpenSpec `openspec-*` skills and `/opsx:*` commands under `.claude/` are used to author and apply the per-feature OpenSpec change.

## Templates And References

Do not invent ad-hoc workflow docs when the standard artifacts apply.

Use:

- `.agents/templates/spec.md` (superseded by `openspec/changes/<NN>/proposal.md`; keep only as a thin pointer)
- `.agents/templates/plan.md` (superseded by `openspec/changes/<NN>/tasks.md`; keep only as a thin pointer)
- `.agents/templates/test_matrix.md`
- `.agents/templates/pr-review.md`
- `.agents/templates/validation-report.md`
- `.agents/templates/pull_request.md`
- `.agents/templates/mistake-entry.md`

And consult:

- `.agents/references/assessment-validation.md`
- `.agents/references/assessment-decisions.md`
- `.agents/references/submission-checklist.md`
- `.agents/references/source-links.md`

## Behavior Rules

- Prefer simple, reviewable solutions over clever abstractions.
- Record decisions once and reuse them.
- Keep review, mistakes, and validation tightly linked.
- Do not silently normalize ambiguous requirements; document the chosen default.
- Never answer provider/model/pricing/limit questions from memory; verify against OpenRouter docs and `.agents/references/source-links.md` (M-009).
- Never log secrets, API keys, JWTs, passwords, or raw document text (M-008).
- Enforce per-user vector isolation on every retrieval (M-005).
- Surface ingestion/parse/embedding failures in BOTH structured logs AND task status (M-006).
- Bound the context sent to the LLM to the retrieved `top_k` chunks (M-007).
