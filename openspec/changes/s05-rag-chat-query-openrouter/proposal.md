# Proposal — s05 RAG chat query (OpenRouter)

> Workstream **05** · branch `feature/05-rag-chat-query-openrouter` · delivery artifacts in `docs/02-features/05-rag-chat/`. Implements RAVID brief **Part 3** (RAG chat engine + credit consumption).

## Why

This is the payoff slice: users ask a question and get an answer grounded ONLY in their own uploaded documents. It connects the per-user Chroma vectors (slice 04) to an LLM via OpenRouter, returns the answer plus `tokens_consumed`, and decrements a per-user credit balance (the brief's "Credit Consumption" / "Subscription Management").

## What Changes

- **`POST /api/chat/query/`** (JWT, JSON `{query}`) → `200 {answer, tokens_consumed}`.
- **Retrieval** (`apps/rag/retrieval.py`): embed the query (same `all-MiniLM-L6-v2` factory) → query the caller's Chroma collection `user_<id>` for `top_k=4` chunks → build a bounded context.
- **LLM via OpenRouter** (`apps/rag/llm.py`): OpenAI-compatible chat/completions at `OPENROUTER_BASE_URL` with `OPENROUTER_MODEL`; `tokens_consumed` read from the response `usage` field (never estimated). Stubbed offline in tests.
- **Credit consumption** (`CreditAccount` model): each user has a balance (default from settings); a successful chat decrements it by `tokens_consumed`. Insufficient balance → `402 {error}` (checked before the LLM call).
- **No-context guard:** if retrieval returns nothing relevant, return a fixed "not enough information in your documents" answer with `tokens_consumed = 0`, NO LLM call and NO charge.
- **Per-user isolation:** retrieval is scoped to the caller's collection only — a user's chat can never surface another user's documents.

## Capabilities

### New Capabilities
- `rag-chat`: owner-scoped retrieval + OpenRouter generation returning `answer` + `tokens_consumed`, with per-user credit consumption and a no-context guard.

### Modified Capabilities
- (none — `authentication` gains a `CreditAccount` but its external contract is unchanged.)

## Impact

- **New code:** `apps/rag/{retrieval,llm,serializers}.py`, `ChatQueryView` in `apps/rag/views.py`, chat route in `apps/rag/urls.py`; `apps/accounts/models.py` `CreditAccount` + migration; settings (`DEFAULT_CHAT_CREDITS`); `config/settings/test.py` (`RAVID_LLM_STUB`); tests.
- **Modified:** `config/urls.py` (uncomment chat route); `tests/smoke/test_endpoints_absent.py` (remove `/api/chat/query/` — now the LAST core endpoint to land).
- **Decisions:** `tokens_consumed` from OpenRouter `usage`; credit check before call + decrement after; no-context guard (no charge); top_k=4; LLM stubbed in tests (offline).
- **Completes RAVID Part 3.** Remaining after this: Docker/delivery (07) and bonus (08).
