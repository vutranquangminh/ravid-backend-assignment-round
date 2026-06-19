# Submission Checklist

Use this as the final go/no-go gate before submitting the RAVID assessment (due **2026-06-20**).
Every box must be checked or explicitly annotated as *not done (with reason)*. Each item points at
the decision it satisfies (see `.agents/references/assessment-decisions.md`) and the validation
command that proves it (see `.agents/references/assessment-validation.md`).

## Core Functionality (RAG)

- [ ] `POST /api/documents/upload/` accepts `.pdf`/`.txt`/`.md` ≤ 10 MB, returns
      `202 {message, document_id, task_id}` [D-017, D-018; V-05]
- [ ] disallowed type / oversize upload rejected with `400 {error}` [D-018, D-022; V-05]
- [ ] ingestion runs async in Celery: load → split (1000/150) → embed (all-MiniLM-L6-v2, 384) →
      Chroma upsert [D-010, D-011, D-025; V-06]
- [ ] `GET /api/documents/status/?task_id=` reports `PROCESSING`/`SUCCESS`/`FAILURE` from the DB row
      [D-019; V-06]
- [ ] ingestion failure surfaces in **both** task status and logs (not swallowed) [D-026; V-06, V-09]
- [ ] `POST /api/chat/query/` retrieves `top_k=4` (cosine), answers grounded in the user's docs,
      returns `200 {answer, tokens_consumed}` [D-012, D-014, D-017; V-07]
- [ ] no-relevant-context guard: chat says there isn't enough information when retrieval is empty
      [D-015; V-07]
- [ ] `tokens_consumed` read from OpenRouter `usage`; per-user credit decremented [D-009, D-016; V-07]
- [ ] **per-user isolation:** user B cannot retrieve user A's chunks; cross-user document/task access
      returns **404 not 403** [D-013, D-020; V-08]

## Authentication

- [ ] `POST /api/register/` works with `{email, password}` → `201 {message, user_id}`
      (no `confirm_password` required) [D-017, D-023; V-03]
- [ ] `POST /api/login/` works → `200 {message, token}`; bad creds → `401 {error}` [D-017; V-03]
- [ ] protected routes (`documents/*`, `chat/*`) require JWT; missing/invalid → `401` [D-021; V-04]

## Observability

- [ ] Django emits structured JSON logs [D-029; V-09]
- [ ] Celery emits JSON logs with task metadata [D-029; V-09]
- [ ] Grafana Alloy ships logs to Loki [D-029; V-09]
- [ ] Grafana datasource is provisioned (from version control)
- [ ] Grafana dashboard is provisioned with a live, service-filterable log stream
- [ ] **no secrets or raw document text appear in any log line** [D-027; V-09]

## Docker And Docs

- [ ] Docker Compose runs the full stack: `web`, `db`, `redis`, `celery`, `chroma`,
      `alloy`/`loki`/`grafana` [V-10]
- [ ] service healthchecks configured where needed; startup order via `service_healthy` [V-10]
- [ ] migrations in sync; `manage.py check` clean [V-11]
- [ ] README contains setup, run, and `.env` instructions
- [ ] API documentation exists (OpenAPI `docs/01-architecture/api_contract.yaml` and/or
      Bruno/Postman — explicit tool choice)
- [ ] `.env.example` lists every required variable (OpenRouter key, DB, Redis, Chroma, etc.)

## Process Artifacts

- [ ] every merged slice has an openspec change archived (`openspec/changes/archive/<NN-name>/`)
- [ ] every slice has its `docs/02-features/<NN-name>/` artifacts: `test_matrix.md`, `pr-review.md`,
      `validation-report.md`, `pull_request.md` [D-024, D-030]
- [ ] one PR per slice into merge-only `main`; all PRs merged
- [ ] validation report current for each slice [V-12]
- [ ] `.agents/MISTAKE.md` reviewed; no unaddressed recurring mistakes [V-12]
- [ ] foundation self-audit scripts pass [V-12]

## Bonus (mark done OR explicitly not-done)

- [ ] chat continuation via `chat_id` implemented — **OR** explicitly marked *not done*
- [ ] SSE streaming on `/api/chat/query/` implemented — **OR** explicitly marked *not done*

---

> If any Core / Auth / Observability / Docker item is unchecked at the deadline, document the gap in
> the relevant `docs/02-features/<NN-name>/validation-report.md` rather than leaving it silent
> (mistake M-003: silent ambiguity; M-004: deferred delivery artifacts).
