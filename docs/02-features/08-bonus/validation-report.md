# Validation Report — 08 Bonus (chat continuation + SSE)

> Branch `feature/08-bonus-chat-continuation-sse` (base `main`). Env: `.venv` + `rag` extra. Offline: stub streaming LLM + stub embeddings + temp Chroma.

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `makemigrations rag` | Conversation/Message migration | ✅ `0002_conversation_message` | checked in |
| `manage.py check` | Django system check | ✅ `0 issues` | re-run independently |
| `python -m pytest -q` | Full suite | ✅ `713 passed` | 93 new bonus tests + 620 prior |
| `ruff check apps/ tests/ config/` | Lint | ✅ `All checks passed!` | — |
| `pre-commit run --all-files` | Hooks | ✅ all pass | — |

## Brief compliance (Bonus Features)

| Feature | Brief | Implemented |
|---------|-------|-------------|
| Chat Continuation API | continue a conversation via `chat_id` / prior history | ✅ `chat_id` on `/api/chat/query/`; Conversation/Message; history in prompt; owner-scoped (404 cross-user) |
| Server-Sent Events streaming | stream responses in real time | ✅ `POST /api/chat/stream/` → `text/event-stream` (`data:` deltas → `done` → `[DONE]`) |

## Failures Or Gaps

- **Real OpenRouter streaming** (`stream=True` + `usage`) runs only with a key in Docker; tests use the deterministic streaming stub (offline).
- No conversation list/rename/delete endpoints (out of scope for the bonus).
- Long-history summarization not implemented — simple last-N-turns window (`CHAT_HISTORY_TURNS`, default 6).

## Mistake check

`No active mistake repeated.` (M-005: conversations + retrieval scoped to `request.user`, cross-user `chat_id` → 404; M-007: history bounded to N turns + top-k context; M-008: no keys/raw context logged; messages persisted only after the full answer is produced, in a transaction — no half-written turns.)
