# Test Matrix — 05 RAG chat query (OpenRouter)

> Spec: `openspec/changes/s05-rag-chat-query-openrouter/`. Implements RAVID Part 3. Tests: stub LLM + stub embeddings + temp Chroma, fully offline.

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Happy | ingest doc → chat | Integration | `200 {answer, tokens_consumed}`; tokens_consumed > 0 == stub usage | `tests/integration/test_chat_api.py` |
| Validation | empty/missing query | Integration | `400 {error}` | same |
| Auth | chat without JWT | Integration | `401 {error}` | same |
| Auth | wrong method GET | Integration | `405 {error}` | same |
| Credits | start balance == DEFAULT_CHAT_CREDITS (lazy) | Integration | created on first use | same |
| Credits | balance decremented by tokens; floored at 0; multi-chat accumulates | Integration | atomic `Greatest(0, balance-tokens)` | same |
| Credits | balance 0 → 402, LLM not called | Integration | `402 {error:"Insufficient credits."}` | same |
| Guard | empty KB → no-context answer | Integration | fixed answer, `tokens_consumed==0`, balance unchanged, LLM NOT called | `TestNoContextGuard` (monkeypatch spy) |
| **Isolation** | A's chat context never contains B's content | Integration | retrieval scoped to `user_<id>` | `TestGroundingIsolation` |
| Unit | retrieve() owner-scoped, respects top_k, empty when no collection | Unit | correct | `tests/unit/test_chat_units.py` |
| Unit | stub LLM deterministic answer + positive tokens; bounded context | Unit | correct | same |
| Observability | LLM errors → 502, logged; no key/context logged | Design | `apps/rag/views.py`, `llm.py` | — |
| Docker | (deferred to slice 07) | — | — | — |
| Regression | `/api/chat/query/` now present; prior endpoints intact | Smoke | present + 404 on bogus path | `tests/smoke/test_endpoints_absent.py` |
| Hygiene | lint/format/commit hooks | Local | all pass | `pre-commit run --all-files` |

**Total:** 572 tests pass (71 new for chat + 501 prior). Offline (stub LLM + stub embeddings + temp Chroma + eager Celery).
