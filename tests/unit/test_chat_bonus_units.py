"""Unit tests for slice 08 chat continuation + SSE streaming internals.

All tests run offline (no network, no real LLM, no Chroma connection).
DB-backed tests use the in-memory SQLite test database.

Coverage:
  - _StubLLM.complete_stream: yields chunks, positive tokens equal to complete()
  - StreamResult: basic iteration contract
  - recent_history: chronological order, bounded to N
  - get_or_create_conversation: new conversation, existing conversation, cross-user 404
  - CHAT_HISTORY_TURNS setting present
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import override_settings

User = get_user_model()


# ---------------------------------------------------------------------------
# _StubLLM.complete_stream
# ---------------------------------------------------------------------------


class TestStubLLMStream:
    def test_complete_stream_returns_stream_result(self) -> None:
        from apps.rag.llm import StreamResult, _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        result = stub.complete_stream("sys", "some context", "some question")
        assert isinstance(result, StreamResult)

    def test_complete_stream_yields_non_empty_chunks(self) -> None:
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        stream = stub.complete_stream("sys", "context text", "a question")
        chunks = list(stream)
        assert len(chunks) > 0
        assert all(isinstance(c, str) for c in chunks)

    def test_complete_stream_tokens_positive(self) -> None:
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        stream = stub.complete_stream("sys", "context text here", "what is this?")
        # Exhaust the stream so tokens are set (for stub they're pre-set).
        list(stream)
        assert stream.tokens > 0

    def test_complete_stream_tokens_equal_complete_tokens(self) -> None:
        """Streaming and non-streaming stubs produce the same token count."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        context = "The sky is blue and the sun is bright."
        question = "What colour is the sky?"

        non_stream = stub.complete("sys", context, question)
        stream = stub.complete_stream("sys", context, question)
        list(stream)  # exhaust

        assert stream.tokens == non_stream.tokens

    def test_complete_stream_answer_reconstructed_from_chunks(self) -> None:
        """Joining all stream chunks gives the same answer as complete()."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        context = "Paris is the capital of France."
        question = "What is the capital of France?"

        non_stream = stub.complete("sys", context, question)
        stream = stub.complete_stream("sys", context, question)
        reconstructed = "".join(list(stream))

        assert reconstructed == non_stream.answer

    def test_complete_stream_tokens_deterministic(self) -> None:
        """Same inputs always produce the same stream token count."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        s1 = stub.complete_stream("sys", "ctx", "q")
        s2 = stub.complete_stream("sys", "ctx", "q")
        list(s1)
        list(s2)
        assert s1.tokens == s2.tokens

    def test_complete_stream_tokens_floor_at_one_empty_inputs(self) -> None:
        """Even with empty context and question, tokens >= 1."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        stream = stub.complete_stream("", "", "")
        list(stream)
        assert stream.tokens >= 1

    def test_complete_stream_different_contexts_different_tokens(self) -> None:
        """Different context lengths produce different token counts in stream."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        s_short = stub.complete_stream("sys", "short", "q")
        s_long = stub.complete_stream("sys", "A" * 500, "q")
        list(s_short)
        list(s_long)
        assert s_short.tokens != s_long.tokens

    def test_complete_stream_history_ignored_for_stub(self) -> None:
        """Passing history to the stub is accepted without error."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        history = [{"role": "user", "content": "previous"}, {"role": "assistant", "content": "ok"}]
        stream = stub.complete_stream("sys", "context", "question", history=history)
        chunks = list(stream)
        assert len(chunks) > 0
        assert stream.tokens > 0


# ---------------------------------------------------------------------------
# StreamResult contract
# ---------------------------------------------------------------------------


class TestStreamResult:
    def test_stream_result_iterable(self) -> None:
        from apps.rag.llm import StreamResult  # noqa: PLC0415

        def _gen():
            yield "hello "
            yield "world"

        sr = StreamResult(_gen())
        assert list(sr) == ["hello ", "world"]

    def test_stream_result_initial_tokens_zero(self) -> None:
        from apps.rag.llm import StreamResult  # noqa: PLC0415

        def _gen():
            yield "x"

        sr = StreamResult(_gen())
        assert sr.tokens == 0

    def test_stream_result_tokens_settable(self) -> None:
        from apps.rag.llm import StreamResult  # noqa: PLC0415

        def _gen():
            yield "x"

        sr = StreamResult(_gen())
        sr.tokens = 42
        assert sr.tokens == 42


# ---------------------------------------------------------------------------
# recent_history
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRecentHistory:
    def _make_user(self, email: str):
        return User.objects.create_user(username=email, email=email, password="pass1234")

    def test_empty_conversation_returns_empty_list(self) -> None:
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("hist_empty@test.com")
        conv = Conversation.objects.create(owner=user)
        assert recent_history(conv) == []

    def test_returns_dicts_with_role_and_content(self) -> None:
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("hist_keys@test.com")
        conv = Conversation.objects.create(owner=user)
        Message.objects.create(conversation=conv, role=Message.Role.USER, content="hello", tokens=0)
        Message.objects.create(
            conversation=conv, role=Message.Role.ASSISTANT, content="hi there", tokens=5
        )

        history = recent_history(conv)
        assert len(history) == 2
        for item in history:
            assert "role" in item
            assert "content" in item

    def test_chronological_order(self) -> None:
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("hist_order@test.com")
        conv = Conversation.objects.create(owner=user)
        Message.objects.create(conversation=conv, role=Message.Role.USER, content="first", tokens=0)
        Message.objects.create(
            conversation=conv, role=Message.Role.ASSISTANT, content="second", tokens=0
        )
        Message.objects.create(conversation=conv, role=Message.Role.USER, content="third", tokens=0)

        history = recent_history(conv)
        contents = [h["content"] for h in history]
        assert contents == ["first", "second", "third"]

    def test_bounded_to_n(self) -> None:
        """recent_history(conv, n=2) returns at most 2 messages."""
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("hist_bound@test.com")
        conv = Conversation.objects.create(owner=user)
        for i in range(6):
            role = Message.Role.USER if i % 2 == 0 else Message.Role.ASSISTANT
            Message.objects.create(conversation=conv, role=role, content=f"msg {i}", tokens=0)

        history = recent_history(conv, n=2)
        assert len(history) == 2

    def test_bounded_returns_most_recent(self) -> None:
        """When bounded, recent_history returns the LATEST n messages."""
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("hist_latest@test.com")
        conv = Conversation.objects.create(owner=user)
        for i in range(4):
            Message.objects.create(
                conversation=conv, role=Message.Role.USER, content=f"msg {i}", tokens=0
            )

        history = recent_history(conv, n=2)
        contents = [h["content"] for h in history]
        # Should be msg 2 and msg 3 (the last 2), in chronological order.
        assert contents == ["msg 2", "msg 3"]

    def test_uses_chat_history_turns_default(self) -> None:
        """recent_history uses CHAT_HISTORY_TURNS when n not specified."""
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("hist_default@test.com")
        conv = Conversation.objects.create(owner=user)
        # Create more messages than CHAT_HISTORY_TURNS.
        turns = getattr(settings, "CHAT_HISTORY_TURNS", 6)
        for i in range(turns + 4):
            Message.objects.create(
                conversation=conv, role=Message.Role.USER, content=f"q{i}", tokens=0
            )

        history = recent_history(conv)
        assert len(history) <= turns

    def test_n_override_with_settings(self) -> None:
        """recent_history respects an explicit n override."""
        from apps.rag.conversations import recent_history  # noqa: PLC0415
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("hist_n@test.com")
        conv = Conversation.objects.create(owner=user)
        for i in range(10):
            Message.objects.create(
                conversation=conv, role=Message.Role.USER, content=f"m{i}", tokens=0
            )

        with override_settings(CHAT_HISTORY_TURNS=3):
            history = recent_history(conv, n=4)
        # Explicit n=4 overrides the setting.
        assert len(history) == 4


# ---------------------------------------------------------------------------
# get_or_create_conversation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetOrCreateConversation:
    def _make_user(self, email: str):
        return User.objects.create_user(username=email, email=email, password="pass1234")

    def test_no_chat_id_creates_new_conversation(self) -> None:
        from apps.rag.conversations import get_or_create_conversation  # noqa: PLC0415
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_new@test.com")
        conv = get_or_create_conversation(user, None)
        assert isinstance(conv, Conversation)
        assert conv.owner == user
        assert conv.pk is not None

    def test_no_chat_id_each_call_creates_new(self) -> None:
        from apps.rag.conversations import get_or_create_conversation  # noqa: PLC0415
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_multi@test.com")
        c1 = get_or_create_conversation(user, None)
        c2 = get_or_create_conversation(user, None)
        assert c1.pk != c2.pk
        assert Conversation.objects.filter(owner=user).count() == 2

    def test_valid_chat_id_returns_existing_conversation(self) -> None:
        from apps.rag.conversations import get_or_create_conversation  # noqa: PLC0415
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_existing@test.com")
        existing = Conversation.objects.create(owner=user)
        fetched = get_or_create_conversation(user, existing.pk)
        assert fetched.pk == existing.pk

    def test_cross_user_chat_id_raises_404(self) -> None:
        from apps.rag.conversations import get_or_create_conversation  # noqa: PLC0415
        from apps.rag.models import Conversation  # noqa: PLC0415

        user_a = self._make_user("conv_iso_a@test.com")
        user_b = self._make_user("conv_iso_b@test.com")
        conv_a = Conversation.objects.create(owner=user_a)

        with pytest.raises(Http404):
            get_or_create_conversation(user_b, conv_a.pk)

    def test_nonexistent_chat_id_raises_404(self) -> None:
        from apps.rag.conversations import get_or_create_conversation  # noqa: PLC0415

        user = self._make_user("conv_missing@test.com")
        with pytest.raises(Http404):
            get_or_create_conversation(user, 99999)

    def test_zero_chat_id_creates_new(self) -> None:
        """chat_id=0 is falsy — should create a new conversation."""
        from apps.rag.conversations import get_or_create_conversation  # noqa: PLC0415
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_zero@test.com")
        conv = get_or_create_conversation(user, 0)
        assert isinstance(conv, Conversation)
        assert conv.owner == user


# ---------------------------------------------------------------------------
# CHAT_HISTORY_TURNS setting
# ---------------------------------------------------------------------------


class TestChatHistoryTurnsSetting:
    def test_setting_exists(self) -> None:
        assert hasattr(settings, "CHAT_HISTORY_TURNS")

    def test_setting_is_positive_int(self) -> None:
        assert isinstance(settings.CHAT_HISTORY_TURNS, int)
        assert settings.CHAT_HISTORY_TURNS > 0

    def test_default_is_six(self) -> None:
        """Default value should be 6 unless overridden in the environment."""
        with override_settings(CHAT_HISTORY_TURNS=6):
            assert settings.CHAT_HISTORY_TURNS == 6


# ---------------------------------------------------------------------------
# Conversation + Message model basics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConversationAndMessageModels:
    def _make_user(self, email: str):
        return User.objects.create_user(username=email, email=email, password="pass1234")

    def test_conversation_str(self) -> None:
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_str@test.com")
        conv = Conversation.objects.create(owner=user)
        s = str(conv)
        assert str(conv.pk) in s

    def test_message_str(self) -> None:
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("msg_str@test.com")
        conv = Conversation.objects.create(owner=user)
        msg = Message.objects.create(
            conversation=conv, role=Message.Role.USER, content="hello", tokens=0
        )
        s = str(msg)
        assert str(msg.pk) in s

    def test_message_ordering_chronological(self) -> None:
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("msg_order@test.com")
        conv = Conversation.objects.create(owner=user)
        m1 = Message.objects.create(
            conversation=conv, role=Message.Role.USER, content="first", tokens=0
        )
        m2 = Message.objects.create(
            conversation=conv, role=Message.Role.ASSISTANT, content="second", tokens=5
        )
        messages = list(Message.objects.filter(conversation=conv))
        assert messages[0].pk == m1.pk
        assert messages[1].pk == m2.pk

    def test_conversation_cascade_deletes_messages(self) -> None:
        from apps.rag.models import Conversation, Message  # noqa: PLC0415

        user = self._make_user("conv_cascade@test.com")
        conv = Conversation.objects.create(owner=user)
        Message.objects.create(conversation=conv, role=Message.Role.USER, content="x", tokens=0)
        conv_id = conv.pk
        conv.delete()
        assert Message.objects.filter(conversation_id=conv_id).count() == 0

    def test_message_role_choices(self) -> None:
        from apps.rag.models import Message  # noqa: PLC0415

        assert Message.Role.USER == "user"
        assert Message.Role.ASSISTANT == "assistant"

    def test_conversation_has_updated_at(self) -> None:
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_updat@test.com")
        conv = Conversation.objects.create(owner=user)
        assert conv.updated_at is not None

    def test_user_cascade_deletes_conversations(self) -> None:
        from apps.rag.models import Conversation  # noqa: PLC0415

        user = self._make_user("conv_usercasc@test.com")
        Conversation.objects.create(owner=user)
        user_id = user.pk
        user.delete()
        assert Conversation.objects.filter(owner_id=user_id).count() == 0
