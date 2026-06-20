# Test Matrix — 08 Bonus (chat continuation + SSE)

> Spec: `openspec/changes/s08-bonus-chat-continuation-sse/`. Implements the brief's Bonus Features. Offline: stub streaming LLM + stub embeddings + temp Chroma.

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Happy | chat without chat_id | Integration | `200 {answer, tokens_consumed, chat_id}`; new Conversation + 2 Messages | `tests/integration/test_chat_continuation_api.py` |
| Happy | continue with chat_id | Integration | appends to same conversation (4 msgs); history passed to LLM | same |
| **Isolation** | B uses A's chat_id | Integration | `404` (no leak); B's convos exclude A's | same |
| Credits | guard turn persisted, 0 tokens, no charge; normal turns decrement; 402 at zero | Integration | correct | same |
| SSE | `/api/chat/stream/` | Integration | `Content-Type: text/event-stream`; `data:` deltas → `done`{chat_id,tokens_consumed} → `[DONE]`; full answer == stub; msgs persisted after; credits deducted | `tests/integration/test_chat_stream_api.py` |
| SSE | continuation via chat_id | Integration | appends to conversation | same |
| SSE | auth/validation/credits | Integration | no token → 401; empty query → 400; zero balance → 402 (no stream) | same |
| Unit | complete_stream stub yields chunks + positive tokens == complete() | Unit | correct | `tests/unit/test_chat_bonus_units.py` |
| Unit | recent_history bounded to N, chronological; get_or_create_conversation (new/existing/404) | Unit | correct | same |
| Regression | `/api/chat/query/` returns `{answer, tokens_consumed, chat_id}`; prior endpoints intact | Integration | additive, backward-compatible | `tests/integration/test_chat_api.py` |
| Hygiene | lint/format/commit hooks | Local | all pass | `pre-commit run --all-files` |

**Total:** 713 tests pass (93 new for bonus + 620 prior). Offline (stub streaming LLM + stub embeddings + temp Chroma + eager Celery).
