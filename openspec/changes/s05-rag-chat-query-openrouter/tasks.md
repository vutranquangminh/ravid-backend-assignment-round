# Tasks — s05 RAG chat query

## 1. Settings
- [ ] 1.1 `base.py`: `DEFAULT_CHAT_CREDITS` (env, default 100000). Reuse `OPENROUTER_BASE_URL/API_KEY/MODEL`, `RETRIEVAL_TOP_K`.
- [ ] 1.2 `test.py`: `RAVID_LLM_STUB = True` (offline LLM); embeddings already stubbed.

## 2. Credit model
- [ ] 2.1 `apps/accounts/models.py`: `CreditAccount(user OneToOne, balance default DEFAULT_CHAT_CREDITS)` + `get_or_create_account(user)`.
- [ ] 2.2 `makemigrations accounts`; check in.

## 3. Retrieval + LLM
- [ ] 3.1 `apps/rag/retrieval.py`: `retrieve(owner_id, query, k)` — embed query → `vectorstore.query` (owner-scoped) → list of {text, document_id}.
- [ ] 3.2 `apps/rag/llm.py`: `get_llm_client()` (real OpenRouter via openai SDK, OpenAI-compatible) + deterministic stub when `RAVID_LLM_STUB`; `complete(system, context, question) -> (answer, tokens)` with tokens from `usage.total_tokens`.

## 4. View + route
- [ ] 4.1 `apps/rag/serializers.py`: `ChatQuerySerializer` (`query` required, non-empty).
- [ ] 4.2 `apps/rag/views.py` `ChatQueryView` (POST, JWT): validate → retrieve → no-context guard (answer + 0 tokens, no charge) → credit check (>0 else 402) → LLM → decrement credits → `200 {answer, tokens_consumed}`.
- [ ] 4.3 `apps/rag/urls.py` add `path("chat/query/", ChatQueryView)`; uncomment in `config/urls.py`.

## 5. Tests (offline: stub LLM + stub embeddings + temp Chroma) — LOTS
- [ ] 5.1 Happy: upload+ingest a doc, then chat → `200 {answer, tokens_consumed}`; tokens_consumed > 0 and equals the stub usage.
- [ ] 5.2 Grounding/isolation: A's chat retrieves only A's chunks; B (different docs) gets different context; a user with no docs hits the no-context guard.
- [ ] 5.3 No-context guard: empty KB → fixed answer, `tokens_consumed == 0`, balance unchanged, LLM NOT called.
- [ ] 5.4 Credits: balance decremented by tokens_consumed; balance at 0 → `402 {error}`; guard path doesn't charge.
- [ ] 5.5 Validation/auth: empty/missing query → 400 `{error}`; no token → 401.
- [ ] 5.6 LLM client: stub returns deterministic answer + tokens; `complete()` builds a bounded prompt from k chunks.
- [ ] 5.7 Regression: `/api/chat/query/` now present; all prior endpoints intact.

## 6. Validate & deliver
- [ ] 6.1 `manage.py check`; full `pytest` green; `ruff check`; `pre-commit` clean.
- [ ] 6.2 `docs/02-features/05-rag-chat/{test_matrix,validation-report,pull_request}.md`.
- [ ] 6.3 PR into `main` (base main, no branch deletion); `openspec archive s05` after merge.
