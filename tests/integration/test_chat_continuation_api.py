"""Integration tests for slice 08 chat continuation via chat_id.

All tests are offline:
  - RAVID_LLM_STUB=True    → deterministic stub, no OpenRouter calls.
  - RAVID_EMBEDDINGS_STUB=True → stub embeddings, no model download.
  - CHROMA_PERSIST_DIR is a temp dir (reset per test by conftest autouse fixture).
  - CELERY_TASK_ALWAYS_EAGER=True → ingestion runs synchronously.

Coverage:
  Continuation:   chat without chat_id → new chat_id; Conversation + 2 Messages created;
                  second call with chat_id appends (4 messages, same conversation);
                  history passed to LLM on continuation (spy check).
  Isolation:      user B passing user A's chat_id → 404;
                  B's conversations never contain A's messages.
  Guard + credits: guard turn persisted with 0 tokens and no charge;
                   normal turns decrement credits;
                   402 at zero balance.
  Regression:     /api/chat/query/ returns {answer, tokens_consumed, chat_id};
                  /api/health/, upload, status still work.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

User = get_user_model()

CHAT_URL = "/api/chat/query/"
UPLOAD_URL = "/api/documents/upload/"
STATUS_URL = "/api/documents/status/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
HEALTH_URL = "/api/health/"

_TXT_GENERIC = b"This is a generic document with some sample text for embedding and retrieval."
_TXT_A = b"The capital of France is Paris. It is a beautiful city on the Seine."
_TXT_B = (
    b"Quantum entanglement is a phenomenon in quantum mechanics. Einstein called it spooky action."
)


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


def _chat(client: Client, token: str, query: str, chat_id: int | None = None) -> object:
    data: dict = {"query": query}
    if chat_id is not None:
        data["chat_id"] = chat_id
    return client.post(
        CHAT_URL,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ---------------------------------------------------------------------------
# Continuation: new chat_id creation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChatContinuation:
    def test_first_chat_returns_chat_id(self) -> None:
        """POST without chat_id → response contains a positive chat_id."""
        token = _register_and_login("cont_first@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "What is this about?")
        assert resp.status_code == 200
        body = resp.json()
        assert "chat_id" in body
        assert isinstance(body["chat_id"], int)
        assert body["chat_id"] > 0

    def test_first_chat_creates_conversation_and_two_messages(self) -> None:
        """After first chat, exactly 1 Conversation and 2 Messages exist."""
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        token = _register_and_login("cont_create@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "What does this say?")
        assert resp.status_code == 200
        conv_id = resp.json()["chat_id"]

        assert Conversation.objects.filter(pk=conv_id).exists()
        msgs = list(Message.objects.filter(conversation_id=conv_id).order_by("created_at"))
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "What does this say?"
        assert msgs[1].role == "assistant"
        assert len(msgs[1].content) > 0

    def test_second_chat_with_same_chat_id_appends_messages(self) -> None:
        """Two chats with the same chat_id share one conversation with 4 messages."""
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        token = _register_and_login("cont_append@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp1 = _chat(client, token, "First question")
        assert resp1.status_code == 200
        chat_id = resp1.json()["chat_id"]

        resp2 = _chat(client, token, "Second question", chat_id=chat_id)
        assert resp2.status_code == 200
        assert resp2.json()["chat_id"] == chat_id

        assert Conversation.objects.filter(pk=chat_id).count() == 1
        msg_count = Message.objects.filter(conversation_id=chat_id).count()
        assert msg_count == 4

    def test_chat_id_consistent_across_calls(self) -> None:
        """Repeated calls with same chat_id keep returning the same chat_id."""
        token = _register_and_login("cont_consistent@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp1 = _chat(client, token, "Q1")
        assert resp1.status_code == 200
        chat_id = resp1.json()["chat_id"]

        for i in range(3):
            resp = _chat(client, token, f"Q{i + 2}", chat_id=chat_id)
            assert resp.status_code == 200
            assert resp.json()["chat_id"] == chat_id

    def test_no_chat_id_each_call_creates_separate_conversation(self) -> None:
        """Calling without chat_id each time creates distinct conversations."""
        from apps.rag.models import Conversation  # noqa: PLC0415

        token = _register_and_login("cont_separate@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp1 = _chat(client, token, "Q1")
        resp2 = _chat(client, token, "Q2")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        id1 = resp1.json()["chat_id"]
        id2 = resp2.json()["chat_id"]
        assert id1 != id2
        assert Conversation.objects.filter(pk__in=[id1, id2]).count() == 2

    def test_history_passed_to_llm_on_continuation(self) -> None:
        """On second chat, the LLM's complete() is called with non-empty history."""
        token = _register_and_login("cont_history@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp1 = _chat(client, token, "Initial question")
        assert resp1.status_code == 200
        chat_id = resp1.json()["chat_id"]

        captured_history: list = []

        original_complete = None

        def spy_complete(self_inner, system, context, question, history=None):
            captured_history.extend(history or [])
            return original_complete(self_inner, system, context, question, history=history)

        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        original_complete = _StubLLM.complete

        with patch.object(_StubLLM, "complete", spy_complete):
            resp2 = _chat(client, token, "Follow-up question", chat_id=chat_id)
        assert resp2.status_code == 200

        # The spy must have captured at least 2 history entries (user + assistant from first turn).
        assert len(captured_history) >= 2
        roles = [h["role"] for h in captured_history]
        assert "user" in roles
        assert "assistant" in roles

    def test_messages_have_correct_content(self) -> None:
        """User messages store the exact query; assistant messages store the answer."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("cont_content@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        query_text = "Please describe the document."
        resp = _chat(client, token, query_text)
        assert resp.status_code == 200
        chat_id = resp.json()["chat_id"]
        answer = resp.json()["answer"]

        msgs = list(Message.objects.filter(conversation_id=chat_id).order_by("created_at"))
        assert msgs[0].role == "user"
        assert msgs[0].content == query_text
        assert msgs[1].role == "assistant"
        assert msgs[1].content == answer

    def test_assistant_message_stores_tokens(self) -> None:
        """The assistant Message row stores the tokens_consumed value."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("cont_tokens@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "What is this?")
        assert resp.status_code == 200
        tokens_resp = resp.json()["tokens_consumed"]
        chat_id = resp.json()["chat_id"]

        asst_msg = Message.objects.filter(
            conversation_id=chat_id, role=Message.Role.ASSISTANT
        ).first()
        assert asst_msg is not None
        assert asst_msg.tokens == tokens_resp


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChatIsolation:
    def test_user_b_cannot_access_user_a_conversation(self) -> None:
        """User B using user A's chat_id must get 404."""
        token_a = _register_and_login("iso_a_cont@test.com")
        token_b = _register_and_login("iso_b_cont@test.com")
        _upload_and_ingest(token_a, _TXT_GENERIC)

        client_a = Client()
        resp_a = _chat(client_a, token_a, "A's question")
        assert resp_a.status_code == 200
        chat_id_a = resp_a.json()["chat_id"]

        client_b = Client()
        resp_b = _chat(client_b, token_b, "B's hijack attempt", chat_id=chat_id_a)
        assert resp_b.status_code == 404
        assert "error" in resp_b.json()

    def test_user_b_conversations_not_visible_to_user_a(self) -> None:
        """User A cannot list or access user B's conversations."""
        from apps.rag.models import Conversation  # noqa: PLC0415

        _register_and_login("iso_vis_a@test.com")
        token_b = _register_and_login("iso_vis_b@test.com")
        _upload_and_ingest(token_b, _TXT_GENERIC)

        user_a = User.objects.get(email="iso_vis_a@test.com")
        user_b = User.objects.get(email="iso_vis_b@test.com")

        client_b = Client()
        _chat(client_b, token_b, "B's conversation")

        b_convs = Conversation.objects.filter(owner=user_b)
        assert b_convs.count() > 0

        a_convs = Conversation.objects.filter(owner=user_a)
        assert a_convs.count() == 0

    def test_cross_user_chat_id_does_not_expose_messages(self) -> None:
        """User B's access attempt to A's chat_id doesn't leak message content."""
        token_a = _register_and_login("iso_leak_a@test.com")
        token_b = _register_and_login("iso_leak_b@test.com")
        _upload_and_ingest(token_a, _TXT_A)

        client_a = Client()
        resp_a = _chat(client_a, token_a, "Paris question")
        assert resp_a.status_code == 200
        chat_id_a = resp_a.json()["chat_id"]

        client_b = Client()
        resp_b = _chat(client_b, token_b, "any query", chat_id=chat_id_a)
        assert resp_b.status_code == 404

    def test_nonexistent_chat_id_returns_404(self) -> None:
        """A chat_id that does not exist in the DB returns 404."""
        token = _register_and_login("iso_nonexist@test.com")
        client = Client()
        resp = _chat(client, token, "query", chat_id=999999)
        assert resp.status_code == 404

    def test_isolation_messages_belong_to_owner(self) -> None:
        """Messages in user A's conversation are only readable via A's owner scope."""
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        token_a = _register_and_login("iso_own_a@test.com")
        _upload_and_ingest(token_a, _TXT_GENERIC)

        user_a = User.objects.get(email="iso_own_a@test.com")

        client_a = Client()
        resp_a = _chat(client_a, token_a, "A's secret question")
        assert resp_a.status_code == 200
        chat_id = resp_a.json()["chat_id"]

        conv = Conversation.objects.get(pk=chat_id, owner=user_a)
        msgs = Message.objects.filter(conversation=conv)
        assert msgs.count() == 2
        for msg in msgs:
            assert msg.conversation.owner == user_a


# ---------------------------------------------------------------------------
# Guard + credits with chat_id
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGuardAndCreditsWithChatId:
    def test_guard_turn_persisted_with_zero_tokens(self) -> None:
        """No-context guard: turn is persisted even though tokens=0."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("guard_persist@test.com")
        # No document uploaded → guard fires.
        client = Client()
        resp = _chat(client, token, "Any question")
        assert resp.status_code == 200
        assert resp.json()["tokens_consumed"] == 0
        chat_id = resp.json()["chat_id"]

        msgs = Message.objects.filter(conversation_id=chat_id)
        assert msgs.count() == 2
        for m in msgs:
            assert m.tokens == 0

    def test_guard_turn_no_credit_charge(self) -> None:
        """Guard turn must not decrement credits."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("guard_no_charge@test.com")
        user = User.objects.get(email="guard_no_charge@test.com")
        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        _chat(client, token, "No docs — guard fires")

        account.refresh_from_db()
        assert account.balance == balance_before

    def test_guard_turn_with_chat_id_appends_to_conversation(self) -> None:
        """A guard turn with an explicit chat_id appends to the given conversation."""
        from apps.rag.models import Message  # noqa: PLC0415

        token = _register_and_login("guard_append@test.com")
        # No docs uploaded.
        client = Client()
        resp1 = _chat(client, token, "Q1 no context")
        assert resp1.status_code == 200
        chat_id = resp1.json()["chat_id"]

        resp2 = _chat(client, token, "Q2 no context", chat_id=chat_id)
        assert resp2.status_code == 200
        assert resp2.json()["chat_id"] == chat_id

        msg_count = Message.objects.filter(conversation_id=chat_id).count()
        assert msg_count == 4

    def test_normal_turn_decrements_credits(self) -> None:
        """After a normal (LLM) chat, credits are decremented."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("credits_deduct_cont@test.com")
        user = User.objects.get(email="credits_deduct_cont@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        resp = _chat(client, token, "Question about the doc")
        assert resp.status_code == 200
        tokens_consumed = resp.json()["tokens_consumed"]
        assert tokens_consumed > 0

        account.refresh_from_db()
        assert account.balance == max(0, balance_before - tokens_consumed)

    def test_zero_balance_returns_402_with_chat_id(self) -> None:
        """With balance=0, providing a valid chat_id still returns 402."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        token = _register_and_login("credits_zero_cont@test.com")
        user = User.objects.get(email="credits_zero_cont@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        # Establish a conversation first (with credits).
        client = Client()
        resp1 = _chat(client, token, "First question")
        assert resp1.status_code == 200
        chat_id = resp1.json()["chat_id"]

        # Drain credits.
        account = get_or_create_account(user)
        CreditAccount.objects.filter(pk=account.pk).update(balance=0)

        resp2 = _chat(client, token, "Second question", chat_id=chat_id)
        assert resp2.status_code == 402
        assert "insufficient credits" in resp2.json()["error"].lower()

    def test_chat_id_in_response_even_on_guard(self) -> None:
        """Guard path must include chat_id in the response."""
        token = _register_and_login("guard_chatid@test.com")
        client = Client()
        resp = _chat(client, token, "No docs here")
        assert resp.status_code == 200
        body = resp.json()
        assert "chat_id" in body
        assert isinstance(body["chat_id"], int)
        assert body["chat_id"] > 0


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegressionSlice08Query:
    def test_chat_query_returns_answer_and_tokens_and_chat_id(self) -> None:
        """/api/chat/query/ response has {answer, tokens_consumed, chat_id}."""
        token = _register_and_login("reg_keys_s08@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "Tell me about the document")
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert "tokens_consumed" in body
        assert "chat_id" in body

    def test_health_endpoint_still_works(self) -> None:
        client = Client()
        resp = client.get(HEALTH_URL)
        assert resp.status_code == 200

    def test_upload_endpoint_still_401_without_jwt(self) -> None:
        client = Client()
        resp = client.post(UPLOAD_URL)
        assert resp.status_code == 401

    def test_status_endpoint_still_401_without_jwt(self) -> None:
        client = Client()
        resp = client.get(STATUS_URL)
        assert resp.status_code == 401

    def test_chat_query_still_401_without_jwt(self) -> None:
        client = Client()
        resp = _post_json(client, CHAT_URL, {"query": "test"})
        assert resp.status_code == 401

    def test_chat_query_still_400_on_empty_query(self) -> None:
        token = _register_and_login("reg_400_s08@test.com")
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": ""}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400

    def test_chat_null_chat_id_works_like_no_chat_id(self) -> None:
        """Sending chat_id=null is equivalent to omitting it (new conversation)."""
        token = _register_and_login("reg_null_chatid@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": "question", "chat_id": None}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        assert "chat_id" in resp.json()
        assert resp.json()["chat_id"] > 0

    def test_chat_stream_endpoint_returns_401_without_jwt(self) -> None:
        """POST /api/chat/stream/ must reject unauthenticated requests."""
        client = Client()
        resp = _post_json(client, "/api/chat/stream/", {"query": "test"})
        assert resp.status_code == 401

    def test_starting_balance_unchanged_in_s08(self) -> None:
        """A freshly registered user still starts with DEFAULT_CHAT_CREDITS."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        _register_and_login("reg_balance_s08@test.com")
        user = User.objects.get(email="reg_balance_s08@test.com")
        acc = get_or_create_account(user)
        assert acc.balance == settings.DEFAULT_CHAT_CREDITS
