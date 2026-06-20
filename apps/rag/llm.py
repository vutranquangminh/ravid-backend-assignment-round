"""LLM client factory for the RAG chat pipeline (slice 05 + 08).

``get_llm_client()`` returns either:
  - A deterministic ``_StubLLM`` when ``settings.RAVID_LLM_STUB`` is True
    (offline tests — no network, no API key).
  - A real ``_OpenRouterClient`` backed by the ``openai`` SDK configured for
    OpenRouter's OpenAI-compatible endpoint (D-007).

Both implement the same two-method contract::

    result = client.complete(system, context, question, history=[])
    # result.answer  -> str
    # result.tokens  -> int > 0

    stream = client.complete_stream(system, context, question, history=[])
    # Iterate stream to receive text chunks; after exhausting, stream.tokens -> int > 0

Secrets are NEVER logged — only counts, statuses, and identifiers (D-027, M-008).
Raw context is also never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatResult:
    """Immutable result from a non-streaming LLM completion call."""

    answer: str
    tokens: int


class StreamResult:
    """Wraps a streaming LLM response.

    Iterate over the instance to receive text chunk strings.
    After the iterator is fully exhausted, ``.tokens`` holds the total token
    count (set by the underlying generator once streaming is done).
    """

    def __init__(self, gen: Iterator[str]) -> None:
        self._gen = gen
        self.tokens: int = 0

    def __iter__(self) -> Iterator[str]:
        yield from self._gen


# ---------------------------------------------------------------------------
# Stub LLM (offline / tests)
# ---------------------------------------------------------------------------


class _StubLLM:
    """Deterministic offline stub — no network, no API key required.

    ``complete`` and ``complete_stream`` produce a fixed answer string that
    references the context length and question, plus a deterministic positive
    token count derived from the lengths of the inputs.

    The token formula (``(len(context) + len(question)) // 4 + len(answer) // 4``)
    is guaranteed to be > 0 for any non-empty context or question.
    We floor at 1 for the pathological edge case of all-empty inputs.
    """

    _ANSWER_TEMPLATE = (
        "Based on the provided context ({ctx_len} chars), "
        "here is the answer to your question: {question_snippet}. "
        "[stub answer — no real LLM was called]"
    )

    def _build_answer_and_tokens(self, context: str, question: str) -> tuple[str, int]:
        snippet = question[:40].strip() if question else "(empty)"
        answer = self._ANSWER_TEMPLATE.format(
            ctx_len=len(context),
            question_snippet=snippet,
        )
        tokens = max(1, (len(context) + len(question)) // 4 + len(answer) // 4)
        return answer, tokens

    def complete(
        self,
        system: str,
        context: str,
        question: str,
        history: list[dict] | None = None,
    ) -> ChatResult:
        """Return a deterministic ChatResult without any network call.

        Args:
            system:   System prompt (used for length accounting only).
            context:  Concatenated retrieved chunks.
            question: The user's raw question text.
            history:  Prior conversation turns (ignored in stub; accepted for API compat).

        Returns:
            A ``ChatResult`` with a stub answer and a positive token count.
        """
        answer, tokens = self._build_answer_and_tokens(context, question)
        return ChatResult(answer=answer, tokens=tokens)

    def complete_stream(
        self,
        system: str,
        context: str,
        question: str,
        history: list[dict] | None = None,
    ) -> StreamResult:
        """Stream the deterministic stub answer word-by-word.

        Splits the same deterministic answer as ``complete()`` into words and
        yields each word (with a trailing space except for the last word).
        After iteration, ``StreamResult.tokens`` equals the same deterministic
        count as ``complete()`` — guaranteed > 0.

        Args:
            system:   System prompt (ignored in stub; accepted for API compat).
            context:  Concatenated retrieved chunks.
            question: The user's raw question text.
            history:  Prior conversation turns (ignored in stub).

        Returns:
            A ``StreamResult`` whose iterator yields text chunks and whose
            ``.tokens`` attribute is set once the iterator is exhausted.
        """
        answer, tokens = self._build_answer_and_tokens(context, question)

        # Pre-compute so the closure captures the final value, not a reference.
        final_tokens = tokens

        def _gen() -> Iterator[str]:
            words = answer.split(" ")
            last = len(words) - 1
            for i, word in enumerate(words):
                yield word if i == last else word + " "

        result = StreamResult(_gen())
        # For the stub the token count is known up front — set it immediately.
        result.tokens = final_tokens
        return result


# ---------------------------------------------------------------------------
# Real OpenRouter client (production)
# ---------------------------------------------------------------------------


class _OpenRouterClient:
    """Real LLM client using the OpenAI SDK pointed at OpenRouter (D-007).

    The ``openai`` package is imported lazily so that the module is still
    importable in environments that don't have it installed — only the stub
    path is needed there.
    """

    def _build_messages(
        self,
        system: str,
        context: str,
        question: str,
        history: list[dict] | None = None,
    ) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            }
        )
        return messages

    def complete(
        self,
        system: str,
        context: str,
        question: str,
        history: list[dict] | None = None,
    ) -> ChatResult:
        """Call OpenRouter chat/completions and return a ChatResult.

        Args:
            system:   System-level instruction for the LLM.
            context:  Concatenated retrieved chunks to use as grounding.
            question: The user's raw question text.
            history:  Prior conversation turns to include before the current question.

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

        messages = self._build_messages(system, context, question, history)

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

    def complete_stream(
        self,
        system: str,
        context: str,
        question: str,
        history: list[dict] | None = None,
    ) -> StreamResult:
        """Stream the LLM response via OpenRouter (SSE / stream=True).

        The generator yields text chunks as they arrive.  After the stream ends
        the ``usage`` chunk (from ``stream_options={"include_usage": True}``) is
        captured and stored in ``StreamResult.tokens``.

        Args:
            system:   System-level instruction for the LLM.
            context:  Concatenated retrieved chunks.
            question: The user's raw question text.
            history:  Prior conversation turns.

        Returns:
            A ``StreamResult``; iterate to get chunks; ``.tokens`` is set after
            the iterator is exhausted.

        Raises:
            Exception: Any network or API error (caller maps to 502).
        """
        from openai import OpenAI  # noqa: PLC0415

        oa_client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

        messages = self._build_messages(system, context, question, history)

        # We need a mutable reference so the generator can set tokens on the
        # StreamResult object after the stream ends.
        result: StreamResult = StreamResult.__new__(StreamResult)
        result.tokens = 0

        def _gen() -> Iterator[str]:
            resp = oa_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=messages,  # type: ignore[arg-type]
                stream=True,
                stream_options={"include_usage": True},
            )
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                if hasattr(chunk, "usage") and chunk.usage is not None:
                    result.tokens = chunk.usage.total_tokens

        result._gen = _gen()  # type: ignore[attr-defined]
        return result


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
