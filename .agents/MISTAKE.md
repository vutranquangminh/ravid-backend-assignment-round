# Mistake Ledger

Use this file as a live memory of avoidable failure patterns in this repository.

## How To Use This File

- Read this file before substantial implementation.
- Read this file again before code review.
- If a review finds a repeated failure pattern, reference the rule ID explicitly using `Repeated mistake: M-XXX`. If none repeated, state `No active mistake repeated.`
- If a new failure pattern appears, add it under `New Incidents` immediately.
- Promote repeated incidents into `Active Rules`.

## Active Rules

### M-001: Path Drift Between Docs, `.agents`, `docs/`, and `openspec/`

- Status: active
- Keywords: `.agent/`, `.agents/`, `docs/02-features`, `openspec/changes`, wrong path, stale path, CSV path
- Failure Pattern: workflow or guidance files reference non-existent or old paths — e.g. `.agent/` instead of `.agents/`, CSV-era folders (`apps/files`, `apps/operations`, `03-csv-upload`) instead of RAVID folders (`apps/documents`, `apps/rag`, `03-document-upload`), or `spec.md`/`plan.md` instead of the OpenSpec `proposal.md`/`design.md`/`tasks.md`.
- Why It Happens: repo conventions drift while docs are updated partially; the CSV reference repo was adapted to RAG and some names were missed.
- Prevention Before Coding: validate every referenced path against the actual repo tree, against `openspec/changes/`, and against the RAVID workstream list; never reintroduce CSV-era names.
- Review Detection Heuristic: search changed docs for `.agent/`, `apps/files`, `apps/operations`, `csv`, `perform-operation`, `upload-csv`, or stale `spec.md`/`plan.md` references that should point at OpenSpec artifacts.
- Last Seen: 2026-06-18

### M-002: Review Done Without Checking `MISTAKE.md`

- Status: active
- Keywords: review, mistake, repeated mistake, M-, declaration string
- Failure Pattern: review is performed without checking active mistake rules first, or without emitting the required declaration string.
- Why It Happens: review is treated as a generic style pass instead of a process gate.
- Prevention Before Coding: treat `MISTAKE.md` as required input for every review; end every review with exactly one of `No active mistake repeated.` or `Repeated mistake: M-XXX`.
- Review Detection Heuristic: review output does not say whether any active mistake repeated, or omits the exact declaration string.
- Last Seen: 2026-06-18

### M-003: Requirement Ambiguity Resolved Silently

- Status: active
- Keywords: assumption, ambiguous, normalize, inferred, undocumented default
- Failure Pattern: the implementation chooses a payload shape, error code, or behavior without documenting the decision.
- Why It Happens: rushing delivery without locking defaults in docs.
- Prevention Before Coding: write ambiguous defaults into `.agents/references/assessment-decisions.md` (and/or the OpenSpec `proposal.md`) before implementation.
- Review Detection Heuristic: code introduces behavior that is absent from the OpenSpec change and `assessment-decisions.md`.
- Last Seen: 2026-06-18

### M-004: Delivery Artifacts Left Until The End

- Status: active
- Keywords: README, OpenAPI, api_contract, docs, dashboard provisioning, test_matrix, validation-report, pr-review, pull_request, opsx:archive
- Failure Pattern: runtime code is built first and delivery docs, dashboards, or the OpenSpec archive step are deferred too long.
- Why It Happens: implementation focus crowds out submission requirements.
- Prevention Before Coding: include delivery artifacts (`docs/02-features/<NN>/` set), README, API docs, and the OpenSpec change in the plan and test matrix from the start.
- Review Detection Heuristic: feature looks complete but README, API docs, dashboard provisioning, the `docs/02-features/<NN>/` artifacts, or the archived OpenSpec change are missing.
- Last Seen: 2026-06-18

### M-005: Cross-User Vector / Chunk Leakage

- Status: active
- Keywords: isolation, per-user, collection, `user_{user_id}`, owner, cross-user, 404, retrieval scope, Chroma
- Failure Pattern: retrieval or upsert touches a collection that is not the authenticated owner's, or a query is not scoped to `user_{user_id}`, leaking one user's chunks/answers to another. Cross-user document/task/vector access returns 403 (leaks existence) or 200 instead of 404.
- Why It Happens: a shared/default Chroma collection is used, the owner filter is dropped, or the retriever is built without the user scope.
- Prevention Before Coding: every retrieval and upsert must resolve the collection name from the authenticated user (`user_{user_id}`) and filter by owner; cross-user access returns 404 not 403.
- Review Detection Heuristic: retriever/collection constructed without the authenticated `user_id`; missing owner FK filter on document/task lookups; tests that do not assert cross-user 404 and per-user collection scoping.
- Last Seen: 2026-06-18

### M-006: Embedding / Parse Failure Swallowed

- Status: active
- Keywords: try/except, swallow, silent failure, task status, FAILURE, ingestion, parse error, embedding error, Celery
- Failure Pattern: a document load, chunk, embed, or Chroma upsert error is caught and ignored, so the task reports SUCCESS (or stays PROCESSING) while no vectors were written. The failure surfaces in neither logs nor task status.
- Why It Happens: broad `except` blocks that log nothing, or that do not propagate the failure to the Celery task state / `IngestionJob` row.
- Prevention Before Coding: any ingestion failure must be surfaced in BOTH structured logs AND task status (`status: FAILURE` with an error message in the `IngestionJob` row); the DB row is the source of truth for status.
- Review Detection Heuristic: bare/broad `except` in the ingestion pipeline; task always returns SUCCESS; no FAILURE-path test; status endpoint cannot report FAILURE.
- Last Seen: 2026-06-18

### M-007: Unbounded Context Sent To The LLM

- Status: active
- Keywords: context window, top_k, prompt size, unbounded, all chunks, token blowup, retrieval limit
- Failure Pattern: the chat prompt stuffs more than the retrieved `top_k=4` chunks (or the whole document) into the LLM call, inflating `tokens_consumed`, cost, and credit burn, and risking context-window overflow.
- Why It Happens: passing the full document or an unlimited retriever result into the prompt instead of the bounded `top_k` chunks.
- Prevention Before Coding: bound the LLM context to the retrieved `top_k=4` cosine-similar chunks; never inline whole documents.
- Review Detection Heuristic: prompt assembly iterates over all chunks/documents rather than the bounded retriever result; no `top_k` limit on the retriever; unexpectedly large `tokens_consumed`.
- Last Seen: 2026-06-18

### M-008: Secret Or Raw Document Text Logged

- Status: active
- Keywords: log, secret, API key, OpenRouter key, JWT, token, password, raw document text, PII, payload, structured logging
- Failure Pattern: structured logs (or error messages) include the OpenRouter/embedding API key, a JWT, a password, or raw document/chunk text — leaking secrets or user content into Loki/Grafana.
- Why It Happens: logging entire request payloads, exception objects, or document contents for debugging convenience.
- Prevention Before Coding: log identifiers and metadata only (document_id, task_id, user_id, chunk count, status); never log keys, tokens, passwords, or raw document/chunk text.
- Review Detection Heuristic: log statements include request bodies, headers, embeddings input text, `Authorization`, API keys, or document content.
- Last Seen: 2026-06-18

### M-009: Provider / Model Details Answered From Memory Instead Of Verified

- Status: active
- Keywords: OpenRouter, model slug, free tier, base url, usage field, embeddings support, from memory, verify, source-links
- Failure Pattern: OpenRouter base url, model slug (free slugs rotate), `usage`/`tokens_consumed` field shape, or "OpenRouter has no embeddings" claims are stated from memory and turn out stale or wrong.
- Why It Happens: relying on training-data recall instead of verifying provider specifics at implementation time.
- Prevention Before Coding: verify provider/model details against OpenRouter docs and `.agents/references/source-links.md`; follow `.agents/guidelines/llm-provider-guidelines.md`. Use the locked values in `assessment-decisions.md` and re-verify rotating free slugs at impl time. Read `tokens_consumed` from the response `usage` field, never estimate.
- Review Detection Heuristic: provider/model values appear inline without a source link or assessment-decisions reference; an estimated token count instead of the `usage` field; an assumed embeddings endpoint on OpenRouter.
- Last Seen: 2026-06-18

## New Incidents

Add fresh mistakes here before promoting them to active rules.

Template:

- Date:
- Title:
- Context:
- Failure:
- Candidate keywords:
- Proposed prevention:

## Retired Rules

Move rules here only after repeated clean passes show they are no longer recurring.
