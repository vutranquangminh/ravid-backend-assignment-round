# Pull Request — 08 Bonus (chat continuation + SSE)

## Progress Snapshot
- **Workstream:** 08 — bonus (chat_id continuation + SSE streaming)
- **Branch (source → target):** `feature/08-bonus-chat-continuation-sse` → `main`
- **OpenSpec change:** `s08-bonus-chat-continuation-sse` (validated)
- **Status:** ready for review
- **Validation:** `manage.py check` clean · `pytest` 713 passed · `ruff` clean · `pre-commit` clean
- **Next:** none — RAVID Parts 1–4 + both bonus features delivered

## Summary
Both brief bonus features: multi-turn conversations addressable by `chat_id` (owner-scoped, history-aware) and real-time SSE streaming of answers — reusing the slice-05 retrieval, credit, guard, and isolation logic.

## Scope
**In:** `Conversation`/`Message` models, `chat_id` on `/api/chat/query/` (history + persistence + returned `chat_id`), `/api/chat/stream/` SSE, streaming LLM client (+ offline stub), 93 tests.
**Out:** conversation management endpoints, history summarization, real OpenRouter streaming in tests.

## Key Changes
- `apps/rag/models.py` (Conversation, Message) + `migrations/0002_*`.
- `apps/rag/conversations.py` (resolve + history helpers); `apps/rag/llm.py` (`complete_stream` + `StreamResult`).
- `apps/rag/views.py` (`ChatQueryView` chat_id; `ChatStreamView` SSE), `serializers.py`, `urls.py`, `config/settings/base.py` (`CHAT_HISTORY_TURNS`).
- `tests/integration/test_chat_continuation_api.py`, `tests/integration/test_chat_stream_api.py`, `tests/unit/test_chat_bonus_units.py`; slice-05 chat tests updated for the additive `chat_id`.

## Reviewer Steps
```bash
.venv/bin/pip install -e '.[rag,dev]'
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
.venv/bin/python -m pytest -q             # 713 passed
pre-commit run --all-files
```
Then: chat once (get `chat_id`) → chat again with that `chat_id` (continuation); `POST /api/chat/stream/` and watch the `data:` events; try another user's `chat_id` → 404.

## Validation
See `docs/02-features/08-bonus/validation-report.md`.

## Submission Readiness
- [x] OpenSpec change validated
- [x] Chat continuation (chat_id, history, owner-scoped 404)
- [x] SSE streaming (`text/event-stream`, done + [DONE])
- [x] Backward-compatible `/api/chat/query/`
- [x] Tests green (713), check clean, lint/hooks clean
- [ ] Merged to main; `openspec archive s08-...` after merge
