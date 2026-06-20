# Design — s08 Bonus: chat continuation + SSE

## Context

Slice 05 delivered single-turn RAG chat (`/api/chat/query/` → `{answer, tokens_consumed}`) with owner-scoped retrieval, credit consumption, and a no-context guard. This slice adds memory (`chat_id`) and streaming, reusing that machinery. Tests stay offline (stub LLM incl. a streaming stub).

## Goals / Non-Goals

**Goals:**
- Continue a conversation by `chat_id`, with prior turns informing the answer; owner-scoped (cross-user → 404).
- Stream answers via SSE for real-time UX.
- Backward-compatible `/api/chat/query/` (chat_id optional; new `chat_id` in response).
- Reuse retrieval, credit, guard, isolation from slice 05; offline deterministic tests.

**Non-Goals:**
- No websockets; SSE only. No conversation listing/rename/delete endpoints (out of scope unless trivial). No summarization of long histories (simple last-N window).

## Decisions

- **Models (`apps/rag/models.py`):** `Conversation(owner=FK(User,CASCADE,related_name="conversations"), created_at, updated_at)`. `Message(conversation=FK(Conversation,CASCADE,related_name="messages"), role=CharField(choices=USER/ASSISTANT), content=TextField, tokens=PositiveIntegerField(default=0), created_at)`. Ordered by `created_at`.
- **Conversation resolution:** helper `get_or_create_conversation(user, chat_id)` — `chat_id` None → create new; else `get_object_or_404(Conversation, pk=chat_id, owner=user)` (cross-user/missing → 404 via the envelope handler). Used by both query + stream.
- **History:** include the last `CHAT_HISTORY_TURNS` (default 6) messages of the conversation as prior chat turns in the LLM prompt, BEFORE the retrieved context + current question. Bounded (M-007).
- **Persistence:** within a DB transaction, append a `user` Message (the query) and, after generation, an `assistant` Message (the answer + its tokens). Persist on BOTH the normal and no-context-guard paths so history is complete. Update `Conversation.updated_at`.
- **`ChatQueryView` changes:** accept optional `chat_id`; resolve/create conversation; build history; (guard → store + return `{answer, tokens_consumed:0, chat_id}`); else credit-check → LLM → deduct → store → `{answer, tokens_consumed, chat_id}`.
- **`ChatStreamView` (`POST /api/chat/stream/`, IsAuthenticated):** returns a `StreamingHttpResponse(content_type="text/event-stream")`. Sequence: resolve conversation + retrieve + (guard or credit-check) → stream the answer as `data: {"delta": "<chunk>"}\n\n` events → final `data: {"event":"done","chat_id":<id>,"tokens_consumed":<n>}\n\n` → `data: [DONE]\n\n`. After the generator finishes, persist messages + deduct credits. Set `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- **LLM client streaming (`apps/rag/llm.py`):** `complete_stream(system, context, question, history) -> Iterator[str]` plus a way to read the final token count (e.g. a small object holding `.tokens` after iteration, or yield a final sentinel). Stub: split a deterministic answer into words, yield each; tokens deterministic and > 0. Real: `openai` `chat.completions.create(stream=True, stream_options={"include_usage": True})`, yield `choice.delta.content`, capture `usage.total_tokens` from the final chunk.
- **Isolation/credit/guard:** identical rules to slice 05 — retrieval scoped to `request.user`; balance ≤ 0 → 402 (for stream, emit an error event or 402 before streaming starts); guard answer not charged.
- **Settings:** `CHAT_HISTORY_TURNS` (env, default 6).

## Risks / Trade-offs

- **SSE under DRF:** APIView can return `StreamingHttpResponse` directly; auth/permission run before streaming. DRF content negotiation is bypassed for the stream response — acceptable.
- **DB writes inside a streaming generator:** persist AFTER the generator completes (collect the full answer while streaming), not mid-stream, to avoid half-written turns; wrap in a transaction.
- **Test consumption:** Django's test client exposes `response.streaming_content` (byte iterator) → tests assert the `data:` events and the final/`[DONE]` markers deterministically with the stub.
- **402 mid-stream:** check credits BEFORE starting the stream so we can return a normal `402 {error}` instead of an error event.
