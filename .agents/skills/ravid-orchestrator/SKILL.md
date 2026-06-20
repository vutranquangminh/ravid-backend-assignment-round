---
name: ravid-orchestrator
description: Orchestrate work for the R.A.V.I.D. RAG-chatbot backend assessment. Use when implementing or planning any part of this project so the agent runs Phase 0 session resume, reads the .agents contract files and the active OpenSpec change, locks ambiguous defaults, ensures the OpenSpec change plus docs/02-features delivery artifacts exist, then hands off to exactly one delivery skill and finally to review-mistake-guard.
---

# RAVID Orchestrator

## Purpose

This is the router skill for the assessment. Use it before substantial feature work so the agent does not re-decide the stack, scope, or workflow on every turn. It coordinates the hybrid OpenSpec + branch/PR workflow: OpenSpec owns proposal/design/tasks per slice, and `docs/02-features/<NN-name>/` owns the QA/review/validation/PR artifacts.

The orchestrator plans and routes. It does not implement endpoints, pipelines, or infra itself; it selects one delivery skill per pass.

## Phase 0: Session Resume

Before choosing the next task, gather progress in this order:

1. Current branch and `git status --short --branch`
2. `docs/00-anchor/task.md`
3. Recent history from `git log --oneline --decorate --max-count=15`
4. `docs/00-anchor/srs.md`
5. `.agents/references/assessment-decisions.md`
6. `openspec/changes/` listing, and the active change's `proposal.md`, `design.md`, `tasks.md`
7. Any non-empty docs under `docs/02-features/01-foundation-django-langchain-bootstrap/` through `docs/02-features/08-bonus-chat-continuation-sse/`
8. `docs/00-anchor/brd.md`, `docs/00-anchor/srs.md`, and `docs/00-anchor/glossary.md` when the task depends on requirements or terminology

If `docs/00-anchor/task.md` conflicts with branch state or git history, report the mismatch and use repo truth for execution until docs are updated.

## Required Read Order

1. `docs/00-anchor/srs.md`
2. `.agents/AGENTS.md`
3. `.agents/WORKFLOW.md`
4. `.agents/MISTAKE.md`
5. `.agents/references/assessment-validation.md`
6. `.agents/references/assessment-decisions.md`
7. `docs/00-anchor/task.md`
8. The active `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}` if the change exists
9. `docs/02-features/<NN-name>/*` if the folder exists and contains non-empty files
10. `docs/00-anchor/brd.md`, `docs/00-anchor/srs.md`, and `docs/00-anchor/glossary.md` when the task depends on requirements or terminology

Source-of-truth precedence: the OpenSpec change (proposal/design/tasks) supersedes any older `spec.md`/`plan.md` content. Reference the OpenSpec change rather than duplicating it. The DB row and the OpenRouter `usage` field are runtime sources of truth; never estimate tokens or trust client-supplied status.

## Responsibilities

### Identify the current workstream

Map the task to one of the RAVID slices:

- `00-foundation` (branch/PR workflow, `.agents/` operating system, docs)
- `01-foundation-django-langchain-bootstrap`
- `02-authentication-register-login-jwt`
- `03-document-upload-pdf-txt-md`
- `04-ingestion-pipeline-chunk-embed-chroma`
- `05-rag-chat-query-openrouter`
- `07-docker-and-delivery-compose-ci`
- `08-bonus-chat-continuation-sse`

### Ensure the OpenSpec change exists

Each feature slice is an OpenSpec change at `openspec/changes/<NN-name>/`:

- If the change does not exist, author it via `/opsx:propose` (or the `openspec-propose` skill) before any `/opsx:apply` implementation. Confirm `proposal.md`, `design.md`, and `tasks.md` are present.
- Implementation runs via `/opsx:apply`. Once the slice ships and merges, archive via `/opsx:archive`.

### Ensure the delivery artifacts exist

Ensure the `docs/02-features/<NN-name>/` folder holds (created or updated):

- `test_matrix.md`
- `pr-review.md`
- `validation-report.md`
- `pull_request.md`

Do not duplicate proposal/design/tasks under `docs/02-features`; those live in the OpenSpec change. The delivery folder is QA/review/validation/PR only.

### Lock decisions

Lock ambiguous decisions into `.agents/references/assessment-decisions.md` before coding. The canonical locked values already include: OpenRouter base url `https://openrouter.ai/api/v1` with model slug `meta-llama/llama-3.3-70b-instruct:free` (verify free slug at impl time), local HuggingFace `all-MiniLM-L6-v2` embeddings (384 dims), `RecursiveCharacterTextSplitter` chunk_size=1000/overlap=150, retrieval top_k=4 cosine, one Chroma collection per user `user_{user_id}`, uploads `.pdf/.txt/.md` max 10 MB, 404-not-403 leak rule, `{"error": "<message>"}` envelope, and per-user credit deduction by `tokens_consumed`.

### Hand off

- Select the next project-specific delivery skill instead of doing everything in one pass.
- Before review, hand off to `review-mistake-guard`.
- Map legacy branch aliases (for example `feature/foundation-*`) to the numbered workstream folders and OpenSpec change names during resume.

## Skill Routing Table

Route to exactly one delivery skill per pass:

- DRF endpoints, serializers, auth, register/login/JWT, upload contract, permissions, response shapes -> `django-api-delivery`
- Upload validation, Celery queuing, LangChain load/split/embed, per-user Chroma upsert, task-status state machine, failure propagation -> `rag-ingestion-pipeline`
- Owner-scoped retrieval, bounded top_k context, OpenRouter call, answer + tokens_consumed + credit deduction, no-context guard, chat_id/SSE -> `rag-chat-retrieval`
- JSON logging, Alloy/Loki/Grafana, Docker Compose (incl. chroma service), README and API-doc delivery hooks -> `observability-compose-delivery`
- Any substantial review of code or docs -> `review-mistake-guard` (always the final handoff before summary)
- Preflight gate before substantial work -> `agent-self-audit`

## Decision Rules

- Prefer the locked stack defaults in `.agents/AGENTS.md` and `.agents/references/assessment-decisions.md`.
- Do not invent alternate architectures unless the user asks.
- If the assessment brief is ambiguous, document the default once in `assessment-decisions.md` and move on (M-003: do not silently resolve ambiguity).
- Never answer provider/model/SDK questions from memory; verify them (M-009).
- Before review, hand off to `review-mistake-guard`.

## Output

Return a short orchestration state:

- `Current branch`
- `Resume sources checked`
- `Current workstream`
- `OpenSpec change` (folder name; proposal/design/tasks present or missing)
- `Completed workstreams`
- `Required docs` (OpenSpec change + docs/02-features delivery artifacts; present or to-be-created)
- `Relevant mistake rules`
- `Open conflicts`
- `Selected skill`
- `Immediate next step`
