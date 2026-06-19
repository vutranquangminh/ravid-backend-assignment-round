# LLM Provider Guidelines (RAVID)

RAVID uses **OpenRouter** as its LLM gateway and **local HuggingFace** embeddings.
These are distinct providers with distinct contracts. The single most important rule:
**verify provider and model facts against current docs at implementation time — never
answer them from memory** (M-009). Free model slugs and free-tier behavior change
without notice.

Canonical locked values: `.agents/references/assessment-decisions.md`. Verification
links: `.agents/references/source-links.md`.

## OpenRouter (chat completions)

- OpenRouter is an **OpenAI-compatible** gateway. Base URL:
  `https://openrouter.ai/api/v1`. Use the OpenAI chat/completions request and response
  shape (`messages: [{role, content}]`, choices, `usage`).
- It is **NOT** the Anthropic Messages API. Do not call `api.anthropic.com`, and do not
  use the Anthropic Messages request shape (`system` top-level + `messages` with
  Anthropic content blocks). If you find an Anthropic-shaped call, it is a bug.
- Model slugs follow `vendor/model:tier`, e.g. `mistralai/mistral-7b-instruct:free` or
  `anthropic/<model>:free`. Free slugs **rotate and get deprecated** — verify the slug
  is currently live before relying on it.
- Authentication is via the OpenRouter API key as a bearer token. The key is read from
  the environment (see `.env.example`); it is never hardcoded and never logged.

### What you MUST verify against OpenRouter docs at impl time

Do not assume any of these — confirm each against the live OpenRouter documentation and
record the check in the slice's `validation-report.md`:

1. The exact base URL and chat/completions path.
2. That the chosen model slug exists and is currently available on the free tier.
3. The request shape (fields, required headers such as any referer/title headers
   OpenRouter recommends).
4. The response shape, specifically **where `tokens_consumed` comes from**: read it from
   the response `usage` field (e.g. `usage.total_tokens`). Confirm the exact field name
   in the response, and **never estimate** token counts.
5. Error response shape and rate-limit behavior for the free tier.

If a fact cannot be verified, stop and resolve it (M-003) rather than guessing.

## Embeddings (local HuggingFace)

- Embeddings are computed **locally** with `all-MiniLM-L6-v2` (384 dimensions) via
  `langchain-huggingface`. They are free, offline, and require **no API key**.
- Do **not** route embeddings through OpenRouter — the OpenRouter free tier provides no
  embeddings endpoint.
- The embedding dimension (384) must match the Chroma collection configuration. A
  dimension mismatch is a correctness bug, not a warning.

## Secrets And Content Safety (hard rules)

- Never log the OpenRouter API key, any bearer token, or full JWTs (M-008).
- Never log raw document text, chunk text, the prompt sent to the model, the model's
  full answer, or computed embeddings. Log ids, the model slug, `tokens_consumed`, and
  `duration_ms` only.
- Never echo secrets in error responses; the error envelope stays `{"error": "..."}`
  with a safe message.
- Keep all keys in environment variables surfaced via `.env.example`; never commit real
  keys.

## Request Discipline

- Bound the context: send only the top_k=4 retrieved chunks (plus the user query, and
  for the bonus, a bounded chat history), never the full corpus or unbounded history
  (M-007).
- Apply the no-relevant-context guard before calling the model: if retrieval returns
  nothing relevant, return the "not enough information in your documents" answer instead
  of calling the LLM to fill gaps.
- After each successful call, read `tokens_consumed` from `usage` and decrement the
  user's credit balance by that amount.

## When This File Applies

The provider here is OpenRouter serving an open-weight model (Mistral) over an
OpenAI-compatible API. Even when a slug names `anthropic/...`, the transport is
OpenRouter's OpenAI-compatible API, not Anthropic's. Treat all model/provider specifics
as facts to verify against OpenRouter docs at implementation time, not facts to recall.
