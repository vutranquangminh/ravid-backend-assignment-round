# Tasks — s08 Bonus: chat continuation + SSE

## 1. Models
- [ ] 1.1 `apps/rag/models.py`: `Conversation(owner FK, created_at, updated_at)` + `Message(conversation FK, role[user|assistant], content, tokens, created_at)` ordered by created_at.
- [ ] 1.2 `makemigrations rag`; check in.

## 2. Conversation + history helpers
- [ ] 2.1 `get_or_create_conversation(user, chat_id)` — new when None; else owner-scoped get_object_or_404 (cross-user/missing → 404).
- [ ] 2.2 `recent_history(conversation, n=settings.CHAT_HISTORY_TURNS)` → last n messages as prompt turns.
- [ ] 2.3 Settings `CHAT_HISTORY_TURNS` (env, default 6).

## 3. LLM streaming
- [ ] 3.1 `apps/rag/llm.py`: `complete_stream(system, context, question, history)` → iterator of text chunks + final token count (stub: deterministic word-by-word, tokens>0; real: openai stream=True + usage).

## 4. Query endpoint (chat_id)
- [ ] 4.1 `serializers.py`: add optional `chat_id` to `ChatQuerySerializer`.
- [ ] 4.2 `ChatQueryView`: resolve/create conversation; build history; persist user+assistant messages (both normal + guard paths) in a transaction; response `{answer, tokens_consumed, chat_id}`.

## 5. Stream endpoint (SSE)
- [ ] 5.1 `ChatStreamView` (`POST /api/chat/stream/`, JWT): credit-check + retrieve + history → `StreamingHttpResponse(text/event-stream)` yielding `data:` delta events, a final `done` event (chat_id, tokens_consumed), then `[DONE]`; persist messages + deduct credits after generation. Headers: no-cache, X-Accel-Buffering: no.
- [ ] 5.2 `config/urls.py`: add `/api/chat/stream/`.

## 6. Tests (offline, stub LLM) — MANY
- [ ] 6.1 Continuation: chat without chat_id → returns a new chat_id; a Conversation + 2 Messages (user+assistant) created; second call WITH that chat_id appends to the same conversation; history is passed to the LLM.
- [ ] 6.2 Isolation: user B using user A's chat_id → 404; B's conversations never include A's.
- [ ] 6.3 Guard + credits with chat_id: guard turn stored, 0 tokens, no charge; credits decremented on real turns; 402 at zero.
- [ ] 6.4 SSE: `/api/chat/stream/` returns `text/event-stream`; streaming_content contains `data:` delta events, a final `done` event with chat_id + tokens_consumed, and `[DONE]`; no token → 401; empty query → 400; zero credits → 402 (no stream).
- [ ] 6.5 SSE continuation: stream with chat_id appends to the conversation; messages persisted after stream completes.
- [ ] 6.6 Unit: `complete_stream` stub yields chunks + positive tokens; `recent_history` bounded to N; `get_or_create_conversation`.
- [ ] 6.7 Regression: `/api/chat/query/` still returns `{answer, tokens_consumed, chat_id}` (chat_id additive); all prior endpoints intact.

## 7. Validate & deliver
- [ ] 7.1 `manage.py check`; full `pytest` green; `ruff check`; `pre-commit`.
- [ ] 7.2 `docs/02-features/08-bonus/{test_matrix,validation-report,pull_request}.md`; note SSE + chat_id in README + API docs.
- [ ] 7.3 PR into `main` (base main, no branch deletion); `openspec archive s08` after merge.
