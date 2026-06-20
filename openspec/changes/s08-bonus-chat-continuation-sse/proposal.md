# Proposal — s08 Bonus: chat continuation (chat_id) + SSE streaming

> Workstream **08** · branch `feature/08-bonus-chat-continuation-sse` · delivery artifacts in `docs/02-features/08-bonus/`. Implements the RAVID brief **Bonus Features**.

## Why

Two bonus features from the brief: (1) **Chat Continuation** — let users continue an existing conversation via a `chat_id` (with prior message history), and (2) **SSE Streaming** — stream the answer in real time for a smoother chat UX. Both build directly on the slice-05 RAG chat.

## What Changes

- **Conversation + Message models** (`apps/rag/models.py`): `Conversation(owner FK, created_at, updated_at)` and `Message(conversation FK, role[user|assistant], content, tokens, created_at)`. Owner-scoped.
- **`POST /api/chat/query/` gains optional `chat_id`:**
  - no `chat_id` → start a new conversation; response includes the new `chat_id`.
  - with `chat_id` → load the caller's conversation (another user's id → `404`), include recent history in the LLM prompt, and append the new turn.
  - response becomes `{answer, tokens_consumed, chat_id}` (additive to slice 05).
  - the user message and assistant answer are persisted to the conversation (including the no-context guard turn).
- **`POST /api/chat/stream/`** (JWT, `{query, chat_id?}`): same retrieval + history + credit logic, but streams the answer as **Server-Sent Events** (`text/event-stream`): incremental `data:` token events, then a final event carrying `chat_id` + `tokens_consumed`, then `[DONE]`.
- **LLM client streaming:** `complete_stream(...)` yields text chunks (real OpenRouter `stream=True`; deterministic word-by-word stub offline) plus a final token count.

## Capabilities

### New Capabilities
- `chat-bonus`: multi-turn conversations addressable by `chat_id` (owner-scoped, history-aware) and real-time SSE streaming of answers — both with the same per-user isolation, credit consumption, and no-context guard as slice 05.

### Modified Capabilities
- (none — `/api/chat/query/` gains an optional field + `chat_id` in the response, fully backward-compatible with slice 05.)

## Impact

- **New:** `Conversation`/`Message` models + migration; `ChatStreamView` + `/api/chat/stream/` route; `complete_stream` in `apps/rag/llm.py`; conversation-history helper; tests.
- **Modified:** `apps/rag/views.py` (`ChatQueryView` chat_id handling), `apps/rag/serializers.py` (optional `chat_id`), `config/urls.py` (stream route), api docs.
- **Decisions:** history bounded to the last N turns; messages persisted on both normal and guard paths; SSE event shape; cross-user `chat_id` → 404.
- **Optional bonus** — Parts 1–4 are already complete; this is upside.
