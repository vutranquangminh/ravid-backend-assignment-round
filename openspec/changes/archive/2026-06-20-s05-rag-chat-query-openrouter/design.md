# Design — s05 RAG chat query

## Context

Slices 03–04 store per-user document vectors in Chroma collections `user_<id>`. This slice answers questions over them: retrieve the caller's relevant chunks, feed them + the question to an OpenRouter LLM, return the answer and the real token usage, and bill the user's credit balance. OpenRouter is OpenAI-compatible (NOT the Anthropic Messages API). Tests stay offline by stubbing the LLM (and reusing the slice-04 stub embeddings).

## Goals / Non-Goals

**Goals:**
- Exact brief contract: `POST /api/chat/query/` `{query}` → `200 {answer, tokens_consumed}`.
- Answers grounded only in the caller's own documents (strict per-user retrieval isolation).
- `tokens_consumed` taken from OpenRouter's `usage`, and a credit balance decremented by it.
- A no-context guard so empty knowledge bases don't hallucinate or get charged.
- Fully offline, deterministic tests.

**Non-Goals:**
- No conversation memory / `chat_id` continuation and no SSE streaming (bonus, slice 08).
- No Docker/real OpenRouter calls in tests (slice 07 runs the real stack).
- No re-ranking or multi-collection retrieval.

## Decisions

- **Endpoint:** `ChatQueryView` (APIView, `IsAuthenticated`). Body `{query: str}`; empty/whitespace → `400 {error:"query is required."}`.
- **Retrieval:** `apps/rag/retrieval.py::retrieve(owner_id, query, k)` → `get_embeddings().embed_query(query)` → `vectorstore.query(owner_id, vec, k=settings.RETRIEVAL_TOP_K)` → list of `{text, document_id}`. Scoped to the caller's collection ONLY (M-005).
- **No-context guard:** if retrieval returns zero chunks → respond `200 {"answer": "I couldn't find anything relevant in your documents to answer that.", "tokens_consumed": 0}`; do NOT call the LLM and do NOT charge credits.
- **Prompt:** a system instruction ("answer ONLY from the provided context; if it's not there, say you don't know") + the concatenated top-k chunks as context + the user question. Context is bounded to the k chunks (M-007: never dump whole documents).
- **LLM client (`apps/rag/llm.py`):** `get_llm_client()` returns a real client (the `openai` SDK configured with `base_url=settings.OPENROUTER_BASE_URL`, `api_key=settings.OPENROUTER_API_KEY`, model `settings.OPENROUTER_MODEL`) UNLESS `settings.RAVID_LLM_STUB` → a deterministic stub. Interface: `complete(system, context, question) -> ChatResult(answer: str, tokens: int)` where `tokens` comes from `response.usage.total_tokens` (real) or a deterministic count (stub). Verify the OpenRouter request/response shape against its docs at integration time (M-009) — the wire protocol is OpenAI chat/completions, not Anthropic.
- **Credit model:** `apps/accounts/models.py::CreditAccount(user OneToOne CASCADE, balance PositiveIntegerField(default=settings.DEFAULT_CHAT_CREDITS))`; `get_or_create_account(user)` lazily creates it with the default balance (so slice-02 register flow is untouched). Flow: BEFORE calling the LLM, require `balance > 0` else `402 {error:"Insufficient credits."}`; AFTER a successful call, `balance = max(0, balance - tokens_consumed)` via an atomic update. The no-context guard path neither checks nor charges.
- **Response:** `{answer, tokens_consumed}` exactly (brief). (A `sources` list is a possible future add; kept out to match the brief precisely.)
- **Settings:** `DEFAULT_CHAT_CREDITS` (env, default e.g. 100000). `test.py`: `RAVID_LLM_STUB = True`. Reuse `OPENROUTER_*` from `.env.example`.

## Risks / Trade-offs

- **Charge-after-call can dip a low balance to 0:** we gate on `balance > 0` (not on the unknown upcoming cost) and floor at 0 after. Acceptable for the assessment; documented. A stricter pre-auth/hold is out of scope.
- **OpenRouter free models rotate / rate-limit:** the model slug is configurable; tests never hit the network; README documents setting a working free slug.
- **Stub vs real divergence:** the stub mimics the `complete()` contract incl. a `usage`-style token count, so swapping in the real client is config-only.
- **Embedding/LLM failures:** surface as `502 {error}` (or `503`) with a logged reason; never leak keys or raw context (M-008).
