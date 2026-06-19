# Code Review Guidelines (RAVID)

Use this file for all review passes in this repo. RAVID is a RAG document-chatbot
backend; reviews are findings-first, severity-ordered, and mistake-aware.

## Required Inputs

Read these before reviewing:

1. `.agents/MISTAKE.md` (active mistake rules)
2. `.agents/references/assessment-decisions.md` (locked values)
3. `docs/00-anchor/srs.md`
4. The slice's OpenSpec change: `openspec/changes/<NN-name>/{proposal,design,tasks}.md`
5. The slice's delivery folder: `docs/02-features/<NN-name>/`
6. The diff or changed files

## Review Priorities

Focus on, in this order:

- correctness
- behavioral regressions
- requirement misses (against the locked contract and OpenSpec design)
- **per-user isolation and authz leaks** (see RAVID checks below)
- **secret / document-text leakage in logs or responses**
- undocumented assumptions
- missing tests
- other security or privacy issues
- observability gaps
- repeated mistake rules

## Required Output Shape

Review output must contain:

- findings first
- file references (path + line where possible)
- severity ordering (highest first)
- open questions or assumptions
- brief summary only after findings

If there are no findings, say so explicitly and mention residual risks or validation
gaps.

## Mistake Cross-Check

Every review must state one of:

- `No active mistake repeated.`
- `Repeated mistake: M-XXX`

If a new recurring issue class appears:

- add it to `.agents/MISTAKE.md`
- mention that it was added

A review that changes code without updating or consulting the MISTAKE ledger is itself a
repeated mistake (M-002).

## RAVID-Specific Checks (must verify every relevant slice)

### Per-user isolation (highest priority)

- Every queryset for documents/tasks is filtered by `request.user` first.
- Vector retrieval targets only the caller's `user_{user_id}` collection — no merge,
  no fallback, no shared collection (M-005).
- Cross-user access to a document, task, or vector returns `404`, not `403`.
- Missing/invalid JWT returns `401`.

### Secret and content leakage

- No API keys, full JWTs, embeddings, or raw document/chunk text in logs or error
  responses (M-008). Confirm logs carry ids and counts, not content.

### Provider / model verification

- OpenRouter base URL, model slug, request shape, and the `usage`/`tokens_consumed`
  field are verified against OpenRouter docs, not asserted from memory (M-009). Flag any
  provider/model claim that lacks a verification reference.
- `tokens_consumed` is read from the response `usage` field, never estimated.
- OpenRouter is treated as OpenAI-compatible (`/api/v1`), distinct from
  `api.anthropic.com`. Flag any Anthropic Messages-shaped call.

### Ingestion correctness

- Uploads validated (type in `.pdf/.txt/.md`, size <= 10 MB, presence) **before**
  queuing Celery work; rejects return `400 {error}`.
- Chunking uses the locked params (1000 / 150); retrieval uses top_k=4 cosine.
- Parse/embed failures mark the task `FAILURE` and surface in both status and logs
  (M-006); exceptions are not swallowed.
- Context sent to the LLM is bounded to retrieved chunks, not the full corpus or
  unbounded history (M-007).
- No-relevant-context guard is present and tested.

### Contract and delivery

- Exact endpoint names, methods, and response shapes match the locked contract.
- Error envelope is `{"error": "<message>"}` everywhere.
- Celery task-state mapping to `PROCESSING | SUCCESS | FAILURE` is correct.
- Structured JSON logging with the stable fields; Grafana/Loki/Alloy wiring intact.
- Docker Compose health and startup order are sound (DB, Redis, Chroma before app).
- The slice's `docs/02-features/<NN-name>/` artifacts exist and are filled in (M-004).
- The OpenSpec `tasks.md` is fully checked off for the applied change.
- README and API documentation are complete and current.
