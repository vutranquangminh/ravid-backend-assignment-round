# Pull Request — 05 RAG chat query (OpenRouter)

## Progress Snapshot
- **Workstream:** 05 — RAG chat (RAVID Part 3, completes the core)
- **Branch (source → target):** `feature/05-rag-chat-query-openrouter` → `main`
- **OpenSpec change:** `s05-rag-chat-query-openrouter` (validated)
- **Status:** ready for review
- **Validation:** `manage.py check` clean · `pytest` 572 passed · `ruff` clean · `pre-commit` clean
- **Next:** slice 07 — Docker & delivery (Part 4)

## Summary
The RAG payoff: `POST /api/chat/query/` embeds the question, retrieves the caller's top-k chunks from their own Chroma collection, generates an answer via OpenRouter, and returns `{answer, tokens_consumed}` while decrementing a per-user credit balance. A no-context guard avoids hallucination (and charges) when the user has no relevant documents. **Completes RAVID Parts 1–3.**

## Scope
**In:** retrieval, OpenRouter LLM client (+ offline stub), `ChatQueryView`, `CreditAccount` model, credit consumption, no-context guard, 71 tests.
**Out:** `chat_id` continuation + SSE (bonus, slice 08); Docker (slice 07); real OpenRouter calls in tests.

## Key Changes
- `apps/rag/{retrieval,llm,serializers}.py` + `ChatQueryView` + chat route.
- `apps/accounts/models.py` `CreditAccount` + `migrations/0001_initial.py`.
- `config/settings/{base,test}.py` (`DEFAULT_CHAT_CREDITS`, `RAVID_LLM_STUB`), `config/urls.py`.
- `tests/integration/test_chat_api.py`, `tests/unit/test_chat_units.py`; regression flips (chat now present).

## Reviewer Steps
```bash
.venv/bin/pip install -e '.[rag]'
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
.venv/bin/python -m pytest -q             # 572 passed
pre-commit run --all-files
```
Then: register → login → upload+ingest a doc → `POST /api/chat/query/ {"query":"..."}` → `{answer, tokens_consumed}`; ask with no docs → no-context guard; drain credits → 402.

## Validation
See `docs/02-features/05-rag-chat/validation-report.md`.

## Submission Readiness
- [x] OpenSpec change validated
- [x] Part 3 contract exact (`{answer, tokens_consumed}`)
- [x] Owner-scoped retrieval isolation (tested)
- [x] Credit consumption + no-context guard
- [x] Tests green (572), check clean, lint/hooks clean
- [ ] Merged to main (awaiting review)
- [ ] `openspec archive s05-...` after merge
