# Validation Report — 05 RAG chat query

> Branch `feature/05-rag-chat-query-openrouter` (base `main`). Env: `.venv` + `rag` extra. Tests offline: stub LLM (`RAVID_LLM_STUB`) + stub embeddings + temp Chroma.

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `makemigrations accounts` | CreditAccount migration | ✅ `0001_initial` (Create model CreditAccount) | checked in |
| `manage.py check` | Django system check | ✅ `0 issues` | re-run independently |
| `python -m pytest -q` | Full suite | ✅ `572 passed` | 71 new chat tests + 501 prior |
| `ruff check apps/ tests/ config/` | Lint | ✅ `All checks passed!` | — |
| `pre-commit run --all-files` | Hooks | ✅ all pass | — |

## Brief compliance (Part 3)

| Aspect | Brief | Implemented |
|--------|-------|-------------|
| `POST /api/chat/query/` | `{query}` → `200 {answer, tokens_consumed}` | ✅ exact |
| Retrieval | LangChain/vector retriever over the user's docs | ✅ owner-scoped Chroma `user_<id>`, top_k=4 |
| LLM | run query + context through the LLM | ✅ OpenRouter (OpenAI-compatible), stubbed in tests |
| Credit consumption | implied "Credit Consumption" | ✅ per-user `CreditAccount` decremented by tokens (402 when empty) |

## Failures Or Gaps

- **Real OpenRouter not called in tests** — stubbed for offline determinism; the real client (`openai` SDK → `OPENROUTER_BASE_URL`) is config-only and exercised live under Docker (slice 07). Verify the exact free model slug + `usage` shape against OpenRouter docs at that point (M-009).
- **No `chat_id` continuation / SSE** — bonus, slice 08.
- **Charge-after-call** can take a low balance to 0 (gated on `balance > 0`, floored at 0); a pre-auth/hold is out of scope (documented).

## Mistake check

`No active mistake repeated.` (M-005: retrieval scoped to `request.user` — cross-user content never surfaced, tested; M-007: only top_k chunks sent to the LLM, context bounded; M-008: api key / raw context never logged; M-009: OpenRouter wired as OpenAI-compatible, real shape to be verified live in slice 07.)
