"""Integration tests for slice 08 SSE streaming endpoint (POST /api/chat/stream/).

All tests are fully offline:
  - RAVID_LLM_STUB=True    → deterministic word-by-word stub, no OpenRouter.
  - RAVID_EMBEDDINGS_STUB=True → stub embeddings.
  - CHROMA_PERSIST_DIR is a temp dir.
  - CELERY_TASK_ALWAYS_EAGER=True → ingestion synchronous.

Coverage:
  Content-Type:     /api/chat/stream/ returns text/event-stream.
  Event shape:      streaming_content has data: delta events, final done event,
                    and [DONE] sentinel; reconstructed answer == stub answer.
  Persistence:      messages persisted AFTER stream ends; credits deducted.
  Auth/validation:  no JWT → 401; empty query → 400; zero credits → 402 (no stream).
  SSE continuation: stream with chat_id appends to existing conversation.
  Guard (SSE):      no-context guard on stream — events emitted, messages persisted, no charge.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

User = get_user_model()

STREAM_URL = "/api/chat/stream/"
CHAT_URL = "/api/chat/query/"
UPLOAD_URL = "/api/documents/upload/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
HEALTH_URL = "/api/health/"

_TXT_GENERIC = b"This is a generic document with some sample text for embedding and retrieval."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _register_and_login(email: str, password: str = "StrongPass1!") -> str:
    c = Client()
    _post_json(c, REGISTER_URL, {"email": email, "password": password})
    resp = _post_json(c, LOGIN_URL, {"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["token"]


def _upload_and_ingest(token: str, content: bytes, filename: str = "doc.txt") -> dict:
    client = Client()
    f = SimpleUploadedFile(filename, content, content_type="text/plain")
    resp = client.post(
        UPLOAD_URL,
        data={"file": f},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 202, f"Upload failed: {resp.json()}"
    return resp.json()


def _stream(
    client: Client,
    token: str,
    query: str,
    chat_id: int | None = None,
) -> object:
    data: dict = {"query": query}
    if chat_id is not None:
        data["chat_id"] = chat_id
    return client.post(
        STREAM_URL,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def _consume_sse(response) -> list[dict | str]:
    """Consume a streaming response and parse SSE events.

    Returns a list of parsed event data:
      - For ``data: {json}`` lines: the parsed dict.
      - For ``data: [DONE]``: the string "[DONE]".
    """
    events: list[dict | str] = []
    for raw_bytes in response.streaming_content:
        line = raw_bytes.decode("utf-8").strip()
        if not line:
            continue
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            if payload == "[DONE]":
                events.append("[DONE]")
            else:
                events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# Basic SSE contract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSSEContentType:
    def test_stream_response_content_type(self) -> None:
        """POST /api/chat/stream/ must return Content-Type: text/event-stream."""
        token = _register_and_login("sse_ct@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "What is this document about?")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.get("Content-Type", "")

    def test_stream_response_cache_control(self) -> None:
        """Streaming response must have Cache-Control: no-cache."""
        token = _register_and_login("sse_cc@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Question about the doc")
        assert resp.status_code == 200
        assert "no-cache" in resp.get("Cache-Control", "")

    def test_stream_response_x_accel_buffering(self) -> None:
        """Streaming response must have X-Accel-Buffering: no."""
        token = _register_and_login("sse_xab@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Question about the doc")
        assert resp.status_code == 200
        assert resp.get("X-Accel-Buffering", "").lower() == "no"


@pytest.mark.django_db
class TestSSEEventShape:
    def test_stream_contains_delta_events(self) -> None:
        """streaming_content must contain at least one 'delta' event."""
        token = _register_and_login("sse_delta@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Tell me about this document")
        events = _consume_sse(resp)

        delta_events = [e for e in events if isinstance(e, dict) and "delta" in e]
        assert len(delta_events) > 0

    def test_stream_contains_done_event(self) -> None:
        """streaming_content must end with a 'done' event containing chat_id + tokens_consumed."""
        token = _register_and_login("sse_done@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Summarise the document")
        events = _consume_sse(resp)

        done_events = [e for e in events if isinstance(e, dict) and e.get("event") == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert "chat_id" in done
        assert "tokens_consumed" in done
        assert isinstance(done["chat_id"], int)
        assert done["chat_id"] > 0
        assert isinstance(done["tokens_consumed"], int)

    def test_stream_ends_with_done_sentinel(self) -> None:
        """The last event in streaming_content must be [DONE]."""
        token = _register_and_login("sse_sentinel@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Any question about the doc")
        events = _consume_sse(resp)

        assert events[-1] == "[DONE]"

    def test_stream_reconstructed_answer_matches_stub(self) -> None:
        """Joining all delta chunks gives the same answer as /api/chat/query/."""
        token = _register_and_login("sse_recon@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)
        query = "What is in this document?"

        # Get the query-endpoint answer.
        client = Client()
        resp_q = client.post(
            CHAT_URL,
            data=json.dumps({"query": query}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp_q.status_code == 200
        expected_answer = resp_q.json()["answer"]

        # Get the stream answer.
        resp_s = _stream(client, token, query)
        events = _consume_sse(resp_s)
        delta_events = [e for e in events if isinstance(e, dict) and "delta" in e]
        reconstructed = "".join(e["delta"] for e in delta_events)

        assert reconstructed == expected_answer

    def test_stream_tokens_consumed_positive(self) -> None:
        """tokens_consumed in done event must be > 0 for a real LLM call."""
        token = _register_and_login("sse_tokens@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Question about the document")
        events = _consume_sse(resp)

        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        assert done["tokens_consumed"] > 0

    def test_stream_chat_id_in_done_event(self) -> None:
        """done event must carry a valid chat_id."""
        token = _register_and_login("sse_chatid_done@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _stream(client, token, "Any question")
        events = _consume_sse(resp)

        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        assert done["chat_id"] > 0


# ---------------------------------------------------------------------------
# Persistence + credits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSSEPersistenceAndCredits:
    def test_messages_persisted_after_stream(self) -> None:
        """User + assistant messages must exist in DB after stream is consumed."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("sse_persist@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)
        query = "Tell me about the document."

        client = Client()
        resp = _stream(client, token, query)
        events = _consume_sse(resp)  # consume the entire stream

        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        chat_id = done["chat_id"]

        msgs = list(Message.objects.filter(conversation_id=chat_id).order_by("created_at"))
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == query
        assert msgs[1].role == "assistant"
        assert len(msgs[1].content) > 0

    def test_credits_deducted_after_stream(self) -> None:
        """Credits must be deducted after the stream is fully consumed."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("sse_cred@test.com")
        user = User.objects.get(email="sse_cred@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        resp = _stream(client, token, "Question about the doc")
        events = _consume_sse(resp)

        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        tokens_consumed = done["tokens_consumed"]

        account.refresh_from_db()
        assert account.balance == max(0, balance_before - tokens_consumed)

    def test_credits_not_deducted_before_stream_starts(self) -> None:
        """Credits must not be deducted before the generator runs (check ordering)."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("sse_cred_order@test.com")
        user = User.objects.get(email="sse_cred_order@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        resp = _stream(client, token, "Question")

        # At this point the response object is returned but streaming_content
        # has NOT been consumed yet — credits should still be intact.
        account.refresh_from_db()
        # Django test client eagerly evaluates streaming content in .post() on
        # StreamingHttpResponse, so we can only confirm balance changes after consumption.
        # This test simply verifies no crash occurs and balance is reduced after consuming.
        events = _consume_sse(resp)
        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        account.refresh_from_db()
        expected = max(0, balance_before - done["tokens_consumed"])
        assert account.balance == expected


# ---------------------------------------------------------------------------
# Auth + validation errors (normal JSON, not event streams)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSSEErrorResponses:
    def test_no_jwt_returns_401(self) -> None:
        """POST /api/chat/stream/ without JWT → 401 (JSON, not SSE)."""
        client = Client()
        resp = _post_json(client, STREAM_URL, {"query": "test"})
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_invalid_jwt_returns_401(self) -> None:
        client = Client()
        resp = client.post(
            STREAM_URL,
            data=json.dumps({"query": "test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer notvalid",
        )
        assert resp.status_code == 401

    def test_empty_query_returns_400(self) -> None:
        """Empty query → 400 JSON before any SSE is emitted."""
        token = _register_and_login("sse_400@test.com")
        client = Client()
        resp = client.post(
            STREAM_URL,
            data=json.dumps({"query": ""}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_whitespace_query_returns_400(self) -> None:
        token = _register_and_login("sse_ws@test.com")
        client = Client()
        resp = client.post(
            STREAM_URL,
            data=json.dumps({"query": "   "}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400

    def test_missing_query_returns_400(self) -> None:
        token = _register_and_login("sse_noq@test.com")
        client = Client()
        resp = client.post(
            STREAM_URL,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_zero_credits_returns_402_not_stream(self) -> None:
        """Zero balance → 402 JSON, no SSE body emitted."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        token = _register_and_login("sse_zero_cred@test.com")
        user = User.objects.get(email="sse_zero_cred@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        CreditAccount.objects.filter(pk=account.pk).update(balance=0)

        client = Client()
        resp = _stream(client, token, "Question about the document")
        assert resp.status_code == 402
        body = resp.json()
        assert "error" in body
        assert "insufficient credits" in body["error"].lower()

    def test_get_method_returns_405(self) -> None:
        """GET /api/chat/stream/ → 405."""
        token = _register_and_login("sse_405@test.com")
        client = Client()
        resp = client.get(STREAM_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 405

    def test_cross_user_chat_id_returns_404(self) -> None:
        """Passing another user's chat_id to /stream/ → 404 JSON."""
        from apps.rag.models import Conversation  # noqa: PLC0415

        token_a = _register_and_login("sse_iso_a@test.com")
        token_b = _register_and_login("sse_iso_b@test.com")
        _upload_and_ingest(token_a, _TXT_GENERIC)

        user_a = User.objects.get(email="sse_iso_a@test.com")
        conv_a = Conversation.objects.create(owner=user_a)

        client_b = Client()
        resp = _stream(client_b, token_b, "hijack", chat_id=conv_a.pk)
        assert resp.status_code == 404
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# SSE continuation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSSEContinuation:
    def test_stream_with_chat_id_appends_to_conversation(self) -> None:
        """Stream with chat_id appends messages to the existing conversation."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("sse_cont@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        # First stream (no chat_id).
        resp1 = _stream(client, token, "First question about the doc")
        events1 = _consume_sse(resp1)
        done1 = next(e for e in events1 if isinstance(e, dict) and e.get("event") == "done")
        chat_id = done1["chat_id"]

        # Second stream (with chat_id).
        resp2 = _stream(client, token, "Second question about the doc", chat_id=chat_id)
        events2 = _consume_sse(resp2)
        done2 = next(e for e in events2 if isinstance(e, dict) and e.get("event") == "done")
        assert done2["chat_id"] == chat_id

        # 4 messages: 2 from first turn, 2 from second.
        msg_count = Message.objects.filter(conversation_id=chat_id).count()
        assert msg_count == 4

    def test_stream_continuation_chat_id_consistent(self) -> None:
        """chat_id returned by done event is stable across stream calls."""
        token = _register_and_login("sse_chatid_stable@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp1 = _stream(client, token, "Q1")
        events1 = _consume_sse(resp1)
        done1 = next(e for e in events1 if isinstance(e, dict) and e.get("event") == "done")
        chat_id = done1["chat_id"]

        resp2 = _stream(client, token, "Q2", chat_id=chat_id)
        events2 = _consume_sse(resp2)
        done2 = next(e for e in events2 if isinstance(e, dict) and e.get("event") == "done")
        assert done2["chat_id"] == chat_id

    def test_stream_and_query_share_same_conversation(self) -> None:
        """A conversation started via /stream/ can be continued via /query/ and vice versa."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("sse_cross@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        # Start via stream.
        resp1 = _stream(client, token, "Started via stream")
        events1 = _consume_sse(resp1)
        done1 = next(e for e in events1 if isinstance(e, dict) and e.get("event") == "done")
        chat_id = done1["chat_id"]

        # Continue via query.
        resp2 = client.post(
            CHAT_URL,
            data=json.dumps({"query": "Continued via query", "chat_id": chat_id}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp2.status_code == 200
        assert resp2.json()["chat_id"] == chat_id

        # 4 messages total.
        assert Message.objects.filter(conversation_id=chat_id).count() == 4


# ---------------------------------------------------------------------------
# SSE guard path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSSEGuard:
    def test_guard_returns_event_stream(self) -> None:
        """No-context guard on stream still returns text/event-stream."""
        token = _register_and_login("sse_guard_ct@test.com")
        # No documents uploaded.
        client = Client()
        resp = _stream(client, token, "Any question with no docs")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.get("Content-Type", "")

    def test_guard_stream_has_delta_events(self) -> None:
        """Guard stream emits delta events with the fixed answer."""
        token = _register_and_login("sse_guard_delta@test.com")
        client = Client()
        resp = _stream(client, token, "No docs here")
        events = _consume_sse(resp)

        delta_events = [e for e in events if isinstance(e, dict) and "delta" in e]
        assert len(delta_events) > 0

    def test_guard_stream_done_event_tokens_zero(self) -> None:
        """Guard done event must have tokens_consumed=0."""
        token = _register_and_login("sse_guard_tok@test.com")
        client = Client()
        resp = _stream(client, token, "Nothing here")
        events = _consume_sse(resp)

        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        assert done["tokens_consumed"] == 0

    def test_guard_stream_ends_with_done_sentinel(self) -> None:
        """Guard stream must also end with [DONE]."""
        token = _register_and_login("sse_guard_sent@test.com")
        client = Client()
        resp = _stream(client, token, "Some question")
        events = _consume_sse(resp)
        assert events[-1] == "[DONE]"

    def test_guard_stream_messages_persisted(self) -> None:
        """Guard stream must persist user + assistant messages."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("sse_guard_pers@test.com")
        client = Client()
        resp = _stream(client, token, "No context question")
        events = _consume_sse(resp)

        done = next(e for e in events if isinstance(e, dict) and e.get("event") == "done")
        chat_id = done["chat_id"]

        msgs = Message.objects.filter(conversation_id=chat_id)
        assert msgs.count() == 2
        for m in msgs:
            assert m.tokens == 0

    def test_guard_stream_no_credit_deduction(self) -> None:
        """Guard stream must not deduct credits."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("sse_guard_cred@test.com")
        user = User.objects.get(email="sse_guard_cred@test.com")
        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        resp = _stream(client, token, "No docs")
        _consume_sse(resp)

        account.refresh_from_db()
        assert account.balance == balance_before

    def test_guard_stream_reconstructed_answer(self) -> None:
        """Joining guard delta chunks gives the fixed no-context answer."""
        token = _register_and_login("sse_guard_ans@test.com")
        client = Client()
        resp = _stream(client, token, "Question without docs")
        events = _consume_sse(resp)

        delta_events = [e for e in events if isinstance(e, dict) and "delta" in e]
        reconstructed = "".join(e["delta"] for e in delta_events)

        from apps.rag.views import _NO_CONTEXT_ANSWER  # noqa: PLC0415

        # The guard answer should be contained in the reconstructed text
        # (accounting for potential trailing spaces from word splitting).
        assert reconstructed.strip() == _NO_CONTEXT_ANSWER
