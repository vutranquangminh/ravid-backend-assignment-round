"""Unit tests for _OpenRouterClient (the real LLM client) using respx.

The openai SDK uses httpx under the hood, so respx intercepts the HTTP calls
without any network activity (offline / no API key needed).

Coverage targets:
  - apps/rag/llm.py 175-184  (_build_messages with and without history)
  - apps/rag/llm.py 208-242  (complete)
  - apps/rag/llm.py 270-298  (complete_stream)
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from django.test import override_settings

# ---------------------------------------------------------------------------
# Settings overrides required to exercise the real client
# ---------------------------------------------------------------------------

_REAL_LLM_SETTINGS = {
    "RAVID_LLM_STUB": False,
    "OPENROUTER_API_KEY": "test-key-respx",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "OPENROUTER_MODEL": "test/model",
}

_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def _make_completion_response(content: str = "Hello from mock.", tokens: int = 42) -> dict:
    """Build a minimal OpenAI-compatible chat completion response body."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "test/model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 32,
            "total_tokens": tokens,
        },
    }


def _make_sse_chunks(
    deltas: list[str],
    total_tokens: int = 17,
    model: str = "test/model",
) -> bytes:
    """
    Build a raw SSE byte payload the openai SDK can parse.

    The format is: one ``data: {...}`` line per chunk, terminated with
    a final usage chunk and ``data: [DONE]``.
    """
    lines: list[str] = []

    for i, delta in enumerate(deltas):
        chunk = {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": delta}
                    if i == 0
                    else {"content": delta},
                    "finish_reason": None,
                }
            ],
        }
        lines.append(f"data: {json.dumps(chunk)}")

    # Final content-free chunk that signals finish
    finish_chunk = {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 1700000000,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    lines.append(f"data: {json.dumps(finish_chunk)}")

    # Usage chunk (stream_options={"include_usage": True})
    usage_chunk = {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 1700000000,
        "model": model,
        "choices": [],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 12,
            "total_tokens": total_tokens,
        },
    }
    lines.append(f"data: {json.dumps(usage_chunk)}")
    lines.append("data: [DONE]")

    body = "\n\n".join(lines) + "\n\n"
    return body.encode()


# ===========================================================================
# _build_messages
# ===========================================================================


class TestBuildMessages:
    """_build_messages is tested indirectly via complete() but also directly."""

    def test_without_history_has_system_and_user(self) -> None:
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        client = _OpenRouterClient()
        msgs = client._build_messages("sys", "ctx", "q")
        assert msgs[0] == {"role": "system", "content": "sys"}
        assert msgs[-1]["role"] == "user"
        assert "ctx" in msgs[-1]["content"]
        assert "q" in msgs[-1]["content"]

    def test_with_history_inserted_between_system_and_user(self) -> None:
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        client = _OpenRouterClient()
        history = [
            {"role": "user", "content": "prev question"},
            {"role": "assistant", "content": "prev answer"},
        ]
        msgs = client._build_messages("sys", "ctx", "q", history)
        assert msgs[0]["role"] == "system"
        assert msgs[1] == history[0]
        assert msgs[2] == history[1]
        assert msgs[-1]["role"] == "user"

    def test_empty_history_not_inserted(self) -> None:
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        client = _OpenRouterClient()
        msgs_no_history = client._build_messages("sys", "ctx", "q", None)
        msgs_empty_history = client._build_messages("sys", "ctx", "q", [])
        # Both should have exactly 2 messages (system + user)
        assert len(msgs_no_history) == 2
        assert len(msgs_empty_history) == 2


# ===========================================================================
# complete()
# ===========================================================================


@pytest.mark.django_db
class TestOpenRouterClientComplete:
    @respx.mock
    def test_complete_returns_chat_result(self) -> None:
        """complete() parses the mock response into a ChatResult."""
        from apps.rag.llm import ChatResult, _OpenRouterClient  # noqa: PLC0415

        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_make_completion_response("Test answer.", 55))
        )

        with override_settings(**_REAL_LLM_SETTINGS):
            client = _OpenRouterClient()
            result = client.complete("system prompt", "some context", "user question")

        assert isinstance(result, ChatResult)
        assert result.answer == "Test answer."
        assert result.tokens == 55

    @respx.mock
    def test_complete_answer_field(self) -> None:
        """complete() correctly maps choices[0].message.content."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(
                200, json=_make_completion_response("Specific content.", 10)
            )
        )

        with override_settings(**_REAL_LLM_SETTINGS):
            result = _OpenRouterClient().complete("s", "c", "q")

        assert result.answer == "Specific content."

    @respx.mock
    def test_complete_tokens_from_usage(self) -> None:
        """complete() uses usage.total_tokens, not a computed value."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_make_completion_response("a", 123))
        )

        with override_settings(**_REAL_LLM_SETTINGS):
            result = _OpenRouterClient().complete("s", "c", "q")

        assert result.tokens == 123

    @respx.mock
    def test_complete_with_history(self) -> None:
        """complete() accepts and sends conversation history."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_make_completion_response("With history.", 20))
        )

        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ans"}]

        with override_settings(**_REAL_LLM_SETTINGS):
            result = _OpenRouterClient().complete("s", "c", "q", history)

        assert result.answer == "With history."
        assert result.tokens == 20

    @respx.mock
    def test_complete_raises_on_http_error(self) -> None:
        """complete() propagates exceptions so the caller can map to 502."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415
        from openai import APIStatusError  # noqa: PLC0415

        respx.post(_CHAT_URL).mock(return_value=httpx.Response(500, json={"error": "server error"}))

        with (
            override_settings(**_REAL_LLM_SETTINGS),
            pytest.raises(APIStatusError),
        ):
            _OpenRouterClient().complete("s", "c", "q")

    @respx.mock
    def test_complete_empty_content_returns_empty_string(self) -> None:
        """When the model returns null content, answer is empty string."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        body = _make_completion_response("", 5)
        body["choices"][0]["message"]["content"] = None  # type: ignore[index]
        respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, json=body))

        with override_settings(**_REAL_LLM_SETTINGS):
            result = _OpenRouterClient().complete("s", "c", "q")

        assert result.answer == ""


# ===========================================================================
# complete_stream()
# ===========================================================================


@pytest.mark.django_db
class TestOpenRouterClientCompleteStream:
    @respx.mock
    def test_stream_yields_delta_chunks(self) -> None:
        """complete_stream() iterator yields each delta content string."""
        from apps.rag.llm import StreamResult, _OpenRouterClient  # noqa: PLC0415

        sse_body = _make_sse_chunks(["Hello", " world", "!"], total_tokens=17)
        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=sse_body,
                headers={"content-type": "text/event-stream"},
            )
        )

        with override_settings(**_REAL_LLM_SETTINGS):
            client = _OpenRouterClient()
            stream = client.complete_stream("system", "context", "question")

        assert isinstance(stream, StreamResult)
        collected = list(stream)
        assert "Hello" in collected
        assert " world" in collected
        assert "!" in collected

    @respx.mock
    def test_stream_tokens_set_after_exhaustion(self) -> None:
        """StreamResult.tokens is populated from the usage chunk after iteration."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        sse_body = _make_sse_chunks(["chunk1", " chunk2"], total_tokens=42)
        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=sse_body,
                headers={"content-type": "text/event-stream"},
            )
        )

        with override_settings(**_REAL_LLM_SETTINGS):
            stream = _OpenRouterClient().complete_stream("s", "c", "q")

        # Exhaust the iterator
        list(stream)
        assert stream.tokens == 42

    @respx.mock
    def test_stream_with_history(self) -> None:
        """complete_stream() accepts conversation history."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        sse_body = _make_sse_chunks(["answer"], total_tokens=10)
        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=sse_body,
                headers={"content-type": "text/event-stream"},
            )
        )

        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ans"}]

        with override_settings(**_REAL_LLM_SETTINGS):
            stream = _OpenRouterClient().complete_stream("s", "c", "q", history)

        chunks = list(stream)
        assert len(chunks) >= 1

    @respx.mock
    def test_stream_tokens_zero_before_exhaustion(self) -> None:
        """StreamResult.tokens starts at 0 and is only set after full iteration."""
        from apps.rag.llm import _OpenRouterClient  # noqa: PLC0415

        sse_body = _make_sse_chunks(["chunk"], total_tokens=7)
        respx.post(_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=sse_body,
                headers={"content-type": "text/event-stream"},
            )
        )

        with override_settings(**_REAL_LLM_SETTINGS):
            stream = _OpenRouterClient().complete_stream("s", "c", "q")

        # Do NOT iterate — tokens should still be 0
        assert stream.tokens == 0
        # Now exhaust to clean up
        list(stream)
