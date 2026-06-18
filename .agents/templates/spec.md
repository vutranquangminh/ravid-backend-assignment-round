# Spec Template

> Hybrid OpenSpec note: the authoritative proposal/design/tasks for this slice live in
> `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}` (authored via `/opsx:propose`,
> implemented via `/opsx:apply`, archived via `/opsx:archive`). This `spec.md` is a thin
> delivery-side anchor: it captures the Progress Snapshot, contracts, and acceptance criteria
> for QA/PR purposes and REFERENCES the OpenSpec change instead of duplicating its content.
> When OpenSpec and this file disagree, the OpenSpec change wins for proposal/design/tasks;
> `.agents/references/assessment-decisions.md` wins for any locked decision.

## OpenSpec Change

- Change ID: `openspec/changes/<NN-name>/`
- Proposal: `openspec/changes/<NN-name>/proposal.md`
- Design: `openspec/changes/<NN-name>/design.md`
- Tasks: `openspec/changes/<NN-name>/tasks.md`

## Progress Snapshot

- Status:
- Current Branch:
- Last Updated:
- Current Step:
- Next Step:
- Validation State:
- PR/Merge State:

## Goal

- Feature:
- Why it exists:
- What success looks like:

## Contracts

### Endpoints

> One block per endpoint touched by this slice. Use the verbatim paths from
> `.agents/references/assessment-decisions.md` (e.g. `/api/register/`, `/api/login/`,
> `/api/documents/upload/`, `/api/documents/status/`, `/api/chat/query/`). Every error
> response uses the single-field envelope `{"error": "<message>"}`.

- Method:
- Path:
- Auth: (none | JWT Bearer)
- Request: (JSON body or multipart field, validation rules)
- Response: (success status + body shape)
- Errors: (400 validation `{error}`, 401 missing/invalid JWT, 404 cross-user / not found, 413/400 oversize)

## Data Model

- Primary entities: (e.g. User, Document, IngestionJob, ChatSession/ChatMessage)
- Key fields: (include `owner` FK, status enum, `tokens_consumed`, credit balance where relevant)
- Relationships: (owner-FK isolation; per-user Chroma collection `user_{user_id}`)

## Async And Storage Behavior

- Task queue behavior: (Celery task name, when enqueued, retry/idempotency)
- Persistence strategy: (DB row is the source of truth for status; vector store is derived)
- File handling: (allowed types `.pdf .txt .md`, max 10 MB, where stored, cleanup)
- Status transitions: (internal Celery states -> public `PROCESSING|SUCCESS|FAILURE` mapping)

## RAG Pipeline Behavior

> Omit blocks that do not apply to this slice.

- Loading/parsing: (LangChain loader per file type)
- Chunking: (RecursiveCharacterTextSplitter chunk_size=1000, chunk_overlap=150)
- Embedding: (local HuggingFace all-MiniLM-L6-v2, 384 dims)
- Vector upsert/scope: (collection `user_{user_id}`, owner-scoped)
- Retrieval: (top_k=4, cosine; no-relevant-context guard)
- LLM call: (OpenRouter base `https://openrouter.ai/api/v1`, model slug, read `tokens_consumed` from `usage`)
- Credit accounting: (decrement per-user balance by `tokens_consumed`)

## Observability

- Required log fields: (structured JSON; e.g. `request_id`, `user_id`, `task_id`, `document_id`, `event`, `tokens_consumed`; NEVER raw document text, API keys, or embeddings)
- Dashboard expectations: (Alloy -> Loki -> Grafana panels relevant to this slice)
- Failure visibility: (parse/embed/LLM failures surface in BOTH structured logs AND task-status)

## Acceptance Criteria

- [ ]
- [ ]
- [ ]

## Locked Decisions

> Mirror only the decisions exercised by this slice; the canonical list lives in
> `.agents/references/assessment-decisions.md`.

- Decision:
- Reason:

## Open Questions

- None
