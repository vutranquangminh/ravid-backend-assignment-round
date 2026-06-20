"""LLM client factory for the RAG chat pipeline (slice 05).

``get_llm_client()`` returns either:
  - A deterministic ``_StubLLM`` when ``settings.RAVID_LLM_STUB`` is True
    (offline tests — no network, no API key).
  - A real ``_OpenRouterClient`` backed by the ``openai`` SDK configured for
    OpenRouter's OpenAI-compatible endpoint (D-007).

Both implement the same contract::

    result = client.complete(system, context, question)
    # result.answer  -> str
    # result.tokens  -> int > 0 (from response usage in the real client;
    #                            deterministic formula in the stub)

Secrets are NEVER logged — only counts, statuses, and identifiers (D-027, M-008).
Raw context is also never logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatResult:
    """Immutable result from an LLM completion call."""

    answer: str
    tokens: int


# ---------------------------------------------------------------------------
# Stub LLM (offline / tests)
# ---------------------------------------------------------------------------


class _StubLLM:
    """Deterministic offline stub — no network, no API key required.

    ``complete`` returns a fixed answer string that references the context
    length and question, plus a deterministic positive token count derived
    from the lengths of the inputs.

    The token formula (``(len(context) + len(question)) // 4 + len(answer) // 4``)
    is guaranteed to be > 0 for any non-empty context or question.
    To handle the pathological edge case where both context and question are
    empty, we floor at 1.
    """

    _ANSWER_TEMPLATE = (
        "Based on the provided context ({ctx_len} chars), "
        "here is the answer to your question: {question_snippet}. "
        "[stub answer — no real LLM was called]"
    )

    def complete(self, system: str, context: str, question: str) -> ChatResult:
        """Return a deterministic ChatResult without any network call.

        Args:
            system:   System prompt (used for length accounting only).
            context:  Concatenated retrieved chunks.
            question: The user's raw question text.

        Returns:
            A ``ChatResult`` with a stub answer and a positive token count.
        """
        snippet = question[:40].strip() if question else "(empty)"
        answer = self._ANSWER_TEMPLATE.format(
            ctx_len=len(context),
            question_snippet=snippet,
        )
        tokens = max(1, (len(context) + len(question)) // 4 + len(answer) // 4)
        return ChatResult(answer=answer, tokens=tokens)


# ---------------------------------------------------------------------------
# Real OpenRouter client (production)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "Answer ONLY using the information in the provided context. "
    "If the answer is not in the context, say you don't know."
)


class _OpenRouterClient:
    """Real LLM client using the OpenAI SDK pointed at OpenRouter (D-007).

    The ``openai`` package is imported lazily so that the module is still
    importable in environments that don't have it installed — only the stub
    path is needed there.
    """

    def complete(self, system: str, context: str, question: str) -> ChatResult:
        """Call OpenRouter chat/completions and return a ChatResult.

        Args:
            system:   System-level instruction for the LLM.
            context:  Concatenated retrieved chunks to use as grounding.
            question: The user's raw question text.

        Returns:
            A ``ChatResult`` with the model's answer and authoritative
            ``usage.total_tokens`` from the response (D-009).

        Raises:
            Exception: Any network or API error (caller maps to 502).
        """
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            },
        ]

        # Never log the api key, full context, or question content (M-008).
        logger.info(
            "llm: sending chat completion request",
            extra={
                "model": settings.OPENROUTER_MODEL,
                "context_chunks": context.count("\n\n") + 1 if context else 0,
            },
        )

        resp = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=messages,  # type: ignore[arg-type]
        )

        answer: str = resp.choices[0].message.content or ""
        tokens: int = resp.usage.total_tokens  # authoritative (D-009)

        logger.info(
            "llm: chat completion succeeded",
            extra={
                "model": settings.OPENROUTER_MODEL,
                "tokens_consumed": tokens,
            },
        )

        return ChatResult(answer=answer, tokens=tokens)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_llm_client() -> _StubLLM | _OpenRouterClient:
    """Return the appropriate LLM client for the current environment.

    Returns:
        ``_StubLLM`` when ``settings.RAVID_LLM_STUB`` is True (offline/tests).
        ``_OpenRouterClient`` otherwise (production).
    """
    if getattr(settings, "RAVID_LLM_STUB", False):
        return _StubLLM()
    return _OpenRouterClient()
