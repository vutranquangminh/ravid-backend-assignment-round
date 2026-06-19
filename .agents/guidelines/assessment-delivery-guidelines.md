# Assessment Delivery Guidelines (RAVID)

This is a time-boxed take-home: build a RAG document-chatbot backend. Use these rules
to move fast without creating avoidable submission risk. Canonical locked values live
in `.agents/references/assessment-decisions.md`.

## Delivery Priorities

1. Working endpoints and background ingestion (upload -> chunk -> embed -> Chroma)
2. Auth and protected routes (register/login + JWT-gated document and chat APIs)
3. Per-user vector isolation and the RAG query path (retrieve -> LLM -> answer)
4. Dockerized run path (Compose brings up the full stack)
5. Structured observability and Grafana visibility
6. README and API documentation
7. Bonus: chat continuation (`chat_id`) and SSE streaming

## Definition Of Done (RAVID)

A slice is done only when all of the following hold for its scope.

### Part 1 — Auth (slice 02)

- `POST /api/register/` -> `201 {message,user_id}` | `400 {error}`.
- `POST /api/login/` -> `200 {message,token}` | `401 {error}`.
- Protected routes reject missing/invalid JWT with `401`.

### Part 2 — Document upload + ingestion (slices 03, 04)

- `POST /api/documents/upload/` (multipart, field `file`, JWT) ->
  `202 {message,document_id,task_id}` | `400 {error}`.
- Only `.pdf .txt .md` accepted, max 10 MB; everything else `400 {error}` before any
  Celery work is queued.
- `GET /api/documents/status/?task_id=<id>` (JWT) ->
  `{task_id,status,...}` with status in `PROCESSING | SUCCESS | FAILURE`.
- Ingestion runs in Celery: load -> `RecursiveCharacterTextSplitter`(1000/150) ->
  local HuggingFace embed -> Chroma upsert into `user_{user_id}`.
- Parse/embed failures mark the task `FAILURE` and the reason is visible in status + logs.

### Part 3 — RAG chat (slice 05)

- `POST /api/chat/query/` (JSON `{query}`, JWT) -> `200 {answer,tokens_consumed}`.
- Retrieval is top_k=4 cosine, scoped to the caller's collection only.
- No-relevant-context guard: answer that there isn't enough information in the user's
  documents rather than hallucinating.
- `tokens_consumed` is read from the provider `usage` field, never estimated.

### Part 4 — Subscription / credit consumption

- Maintain a per-user credit balance, decremented by actual `tokens_consumed`.

### Cross-cutting (every slice)

- Cross-user access to any resource returns `404`, not `403`.
- Error envelope is `{"error": "<message>"}` everywhere.
- Structured JSON logs flow to Grafana via Alloy -> Loki; no secrets or document text.
- The OpenSpec change for the slice is applied and its `tasks.md` is fully checked off.
- The slice's delivery artifacts exist under `docs/02-features/<NN-name>/`:
  `test_matrix.md`, `pr-review.md`, `validation-report.md`, `pull_request.md`.

### Bonus (slice 08)

- Chat continuation via `chat_id`; SSE streaming endpoint. Optional — never block the
  core slices on it.

## Clarification Standard (lock ambiguity before coding)

- If a requirement is ambiguous and the choice changes the contract, behavior, or data
  model, **stop and resolve it before writing code** (M-003: no silent ambiguity).
- Resolution path, in order:
  1. Check `.agents/references/assessment-decisions.md` for an existing locked value.
  2. Check the assessment PDF / `docs/00-anchor/`.
  3. If still unresolved, record the chosen interpretation and rationale as a new locked
     decision in `assessment-decisions.md`, then proceed.
- Never invent payload behavior, endpoint names, or status codes silently. Once locked,
  use the exact value everywhere and move on.
- For provider/model facts (slugs, base URL, request/response shape, usage field),
  verify against OpenRouter docs at implementation time per
  `.agents/guidelines/llm-provider-guidelines.md` — do not lock from memory (M-009).

## Speed Rules

- Prefer one clean implementation path over multiple optional architectures.
- Keep the number of apps, modules, and custom abstractions low
  (`apps/documents`, `apps/rag`, plus auth).
- Lock ambiguous decisions once in `assessment-decisions.md` and move on.
- Use file provisioning and checked-in config for dashboards and datasources.
- Keep feature and product work off `main`; use short-lived feature branches and PRs.
- Agent operating-system maintenance limited to `AGENTS.md` and `.agents/**` may go
  directly to `main` only when isolated from product changes.

## Non-Negotiables

- Exact assessment endpoints must exist with the exact response shapes above.
- Celery and Redis must be part of the solution.
- Protected routes must require JWT auth.
- Per-user vector isolation must hold; cross-user access returns `404`.
- Logs must be structured and visible through Grafana and Loki.
- Docker Compose must run the required stack.
- README and API docs must be present before final submission.

## Branch And PR Rules

- Every workstream change uses a dedicated branch created from `main`.
- Branch format: `feature/<nn-workstream>-<short-scope>`.
- Roadmap branches: `feature/00-foundation-branch-pr-workflow`,
  `01-foundation-django-langchain-bootstrap`, `02-authentication-register-login-jwt`,
  `03-document-upload-pdf-txt-md`, `04-ingestion-pipeline-chunk-embed-chroma`,
  `05-rag-chat-query-openrouter`, `07-docker-and-delivery-compose-ci`,
  `08-bonus-chat-continuation-sse`.
- Every feature branch opens a PR targeting `main`. `main` is merge-only.
- Do not commit feature work directly to `main`. Direct commits to `main` are allowed
  only for changes limited to `AGENTS.md` and `.agents/**`.
- Each slice = one OpenSpec change (`proposal.md`/`design.md`/`tasks.md`) **and** one
  branch + one PR + the `docs/02-features/<NN-name>/` artifacts. OpenSpec owns the
  proposal/design/tasks; `docs/02-features` owns QA/review/validation/PR artifacts.

## Acceptable Shortcuts

- Use a simple local filesystem storage strategy if documented and works in Docker.
- Use Grafana Alloy directly instead of Promtail because it is current and supported.
- Use a local on-disk Chroma persistence path as long as it survives container restarts
  in the documented Compose setup.

## Unacceptable Shortcuts

- Skipping tests for core endpoint behavior, isolation, or async state transitions.
- Hardcoding undocumented payload behavior or guessing endpoint/provider details.
- Deferring README or API docs until after the app is "done".
- Deferring per-slice delivery artifacts (M-004).
- Estimating `tokens_consumed` instead of reading the provider `usage` field.
- Shipping logs that are unstructured, or that leak secrets or document text.
- Treating review or the MISTAKE ledger as optional.
