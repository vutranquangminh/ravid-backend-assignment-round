---
name: rag-chat-retrieval
description: Build the RAG chat query and retrieval path for the RAVID assessment. Use when working on owner-scoped vector retrieval, bounded top_k context assembly, the OpenRouter LLM call, the answer plus tokens_consumed response, per-user credit deduction, the no-relevant-context guard, and the optional chat_id continuation and SSE streaming.
---

# RAG Chat Retrieval

## Purpose

Use this skill for the synchronous chat/query path (`apps/rag` retrieval side): take a user query, retrieve the owner's relevant chunks from Chroma, build a bounded prompt, call OpenRouter, return the answer with `tokens_consumed`, and deduct credit. Use the ingestion skill for everything that writes vectors.

## Read Before Work

1. `.agents/MISTAKE.md`
2. `.agents/guidelines/llm-provider-guidelines.md`
3. `.agents/references/assessment-decisions.md`
4. The active `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}`
5. `docs/02-features/<NN-name>/test_matrix.md`

## Scope

- owner-scoped retrieval from the user's Chroma collection
- bounded top_k context assembly
- prompt construction
- OpenRouter chat/completions call
- answer + `tokens_consumed` response
- per-user credit balance deduction
- no-relevant-context guard
- optional chat continuation via `chat_id`
- optional SSE streaming (bonus)

## Locked Retrieval / Provider Values

- Retrieval: `top_k=4`, similarity `cosine`. Query ONLY the authenticated owner's collection `user_{user_id}` (M-005: cross-user vector leakage).
- LLM: OpenRouter at base url `https://openrouter.ai/api/v1`, OpenAI-compatible chat/completions shape (NOT the Anthropic Messages shape). Model slug `meta-llama/llama-3.3-70b-instruct:free` (free slugs rotate; verify at impl time).
- Tokens: read `tokens_consumed` from the response `usage` field. Never estimate (M-009 / source-of-truth rule).
- Context is bounded by `top_k` retrieved chunks; never send the user's whole document corpus to the LLM (M-007: unbounded context).

## Endpoint

- `POST /api/chat/query/` — JSON `{query}`; JWT -> `200 {answer, tokens_consumed}`. Missing/invalid JWT -> `401`. Cross-user resource access (for example a `chat_id` you do not own) -> `404`.

## Rules

- Scope retrieval to the authenticated owner's collection only; pass the owner filter to every Chroma query.
- Cap context at `top_k=4` chunks and assemble a single bounded prompt; do not concatenate the whole corpus (M-007).
- Call OpenRouter with the OpenAI-compatible chat/completions request shape and the configured model slug. Do not answer model/provider/SDK questions from memory; verify the slug and shape at implementation time (M-009).
- Read `tokens_consumed` from the response `usage` field and return it in the response. Never estimate or fabricate token counts.
- No-relevant-context guard: if retrieval returns nothing relevant, answer that there is not enough information in the user's documents rather than hallucinating.
- Credit deduction: decrement the per-user credit balance by `tokens_consumed`. Keep the DB row as the source of truth for the balance. Define behavior when credit is exhausted in the OpenSpec change.
- Never log the OpenRouter key, embedding key, raw document text, or raw chunk text (M-008). Log query metadata, chunk ids, token count, and credit delta instead.
- For SSE/`chat_id` continuation (bonus), persist conversation turns scoped to the owner; document the streaming contract before implementing it (M-003).

## Required Checks

- Test that retrieval only returns the owner's chunks (no cross-user leakage)
- Test the no-relevant-context guard answer
- Test that `tokens_consumed` comes from the response `usage` field
- Test that the credit balance is decremented by `tokens_consumed`
- Test 401 (missing/invalid JWT) and 404 (cross-user `chat_id`)
- Test that context is bounded to `top_k` chunks
- Validation that the response shape matches `{answer, tokens_consumed}`

## Output

When this skill is used, the result should include:

- updated retrieval and chat code (owner-scoped query, bounded prompt, OpenRouter call, credit deduction)
- updated provider/retrieval contract in the OpenSpec change if it changed
- updated tests
- updated `docs/02-features/<NN-name>/test_matrix.md` if coverage changed
- validation evidence
