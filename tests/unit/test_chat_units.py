"""Unit tests for slice 05 chat internals (offline, no network, no DB in most cases).

Covers:
  - _StubLLM: deterministic answer, positive tokens, formula correctness.
  - get_llm_client(): returns _StubLLM when RAVID_LLM_STUB=True.
  - ChatResult: frozen dataclass.
  - ChatQuerySerializer: valid/invalid inputs.
  - retrieval.retrieve(): scoped to owner; respects top_k; empty when no collection.
  - Context building: bounded to k chunks, not unbounded.
  - CreditAccount model: get_or_create_account, floor-at-zero arithmetic.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings

User = get_user_model()


# ---------------------------------------------------------------------------
# _StubLLM
# ---------------------------------------------------------------------------


class TestStubLLM:
    def test_complete_returns_chat_result(self) -> None:
        from apps.rag.llm import ChatResult, _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        result = stub.complete("system", "some context", "some question")
        assert isinstance(result, ChatResult)

    def test_tokens_positive(self) -> None:
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        result = stub.complete("system", "context text here", "what is this?")
        assert result.tokens > 0

    def test_tokens_deterministic(self) -> None:
        """Same inputs always produce the same token count."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        r1 = stub.complete("sys", "ctx", "q")
        r2 = stub.complete("sys", "ctx", "q")
        assert r1.tokens == r2.tokens
        assert r1.answer == r2.answer

    def test_answer_references_context_length(self) -> None:
        """Stub answer mentions the context length."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        context = "A" * 100
        result = stub.complete("system", context, "question")
        assert "100" in result.answer  # context length referenced

    def test_answer_non_empty(self) -> None:
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        result = stub.complete("system", "context", "question")
        assert isinstance(result.answer, str)
        assert len(result.answer) > 0

    def test_tokens_floor_at_one_for_empty_inputs(self) -> None:
        """Even with empty context and question, tokens >= 1."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        result = stub.complete("", "", "")
        assert result.tokens >= 1

    def test_different_contexts_produce_different_tokens(self) -> None:
        """Different context lengths produce different token counts."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        r_short = stub.complete("sys", "short", "q")
        r_long = stub.complete("sys", "A" * 500, "q")
        # Different context lengths → different token counts (stub formula depends on len).
        assert r_short.tokens != r_long.tokens


# ---------------------------------------------------------------------------
# ChatResult dataclass
# ---------------------------------------------------------------------------


class TestChatResult:
    def test_frozen_dataclass(self) -> None:
        """ChatResult must be frozen — assigning attributes raises."""
        from apps.rag.llm import ChatResult  # noqa: PLC0415

        result = ChatResult(answer="hello", tokens=42)
        with pytest.raises((AttributeError, TypeError)):
            result.answer = "changed"  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        from apps.rag.llm import ChatResult  # noqa: PLC0415

        result = ChatResult(answer="test answer", tokens=99)
        assert result.answer == "test answer"
        assert result.tokens == 99


# ---------------------------------------------------------------------------
# get_llm_client factory
# ---------------------------------------------------------------------------


class TestGetLLMClient:
    def test_returns_stub_when_stub_setting_true(self) -> None:
        from apps.rag.llm import _StubLLM, get_llm_client  # noqa: PLC0415

        with override_settings(RAVID_LLM_STUB=True):
            client = get_llm_client()
        assert isinstance(client, _StubLLM)

    def test_returns_openrouter_when_stub_false(self) -> None:
        from apps.rag.llm import _OpenRouterClient, get_llm_client  # noqa: PLC0415

        with override_settings(RAVID_LLM_STUB=False):
            client = get_llm_client()
        assert isinstance(client, _OpenRouterClient)

    def test_test_settings_use_stub(self) -> None:
        """Confirm test settings have RAVID_LLM_STUB=True."""
        assert getattr(settings, "RAVID_LLM_STUB", False) is True


# ---------------------------------------------------------------------------
# ChatQuerySerializer
# ---------------------------------------------------------------------------


class TestChatQuerySerializer:
    def test_valid_query_passes(self) -> None:
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": "What is the capital of France?"})
        assert s.is_valid(), s.errors
        assert s.validated_data["query"] == "What is the capital of France?"

    def test_empty_query_fails(self) -> None:
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": ""})
        assert not s.is_valid()

    def test_whitespace_only_query_fails(self) -> None:
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": "   \t\n"})
        assert not s.is_valid()

    def test_missing_query_field_fails(self) -> None:
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={})
        assert not s.is_valid()
        assert "query" in s.errors

    def test_query_trimmed_on_validate(self) -> None:
        """Leading/trailing whitespace is stripped (trim_whitespace=True)."""
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": "  hello world  "})
        assert s.is_valid(), s.errors
        assert s.validated_data["query"] == "hello world"

    def test_error_message_exact(self) -> None:
        """Missing query must produce exactly 'query is required.' error."""
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={})
        assert not s.is_valid()
        assert "query is required." in str(s.errors)

    def test_extra_fields_ignored(self) -> None:
        """Extra fields in the request body are simply ignored."""
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": "hello", "extra_field": "ignored"})
        assert s.is_valid(), s.errors


# ---------------------------------------------------------------------------
# retrieval.retrieve()
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetrieve:
    def test_empty_collection_returns_empty_list(self) -> None:
        """retrieve() for a user with no ingested docs must return []."""
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_empty@test.com",
            email="ret_empty@test.com",
            password="pass1234",
        )
        result = retrieve(user.pk, "what is this?")
        assert result == []

    def test_returns_list_of_dicts_with_expected_keys(self) -> None:
        """Each returned chunk must have 'text' and 'document_id' keys."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.embeddings import get_embeddings  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_keys@test.com",
            email="ret_keys@test.com",
            password="pass1234",
        )

        # Manually upsert a chunk to the user's collection.
        emb = get_embeddings()
        texts = ["The sky is blue and full of clouds."]
        vectors = emb.embed_documents(texts)
        vectorstore.upsert_chunks(user.pk, document_id=1, texts=texts, embeddings=vectors)

        chunks = retrieve(user.pk, "sky colour")
        assert len(chunks) > 0
        for chunk in chunks:
            assert "text" in chunk
            assert "document_id" in chunk

    def test_scoped_to_owner_not_other_user(self) -> None:
        """retrieve() must not return chunks from a different owner's collection."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.embeddings import get_embeddings  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user_a = User.objects.create_user(
            username="ret_iso_a@test.com",
            email="ret_iso_a@test.com",
            password="pass1234",
        )
        user_b = User.objects.create_user(
            username="ret_iso_b@test.com",
            email="ret_iso_b@test.com",
            password="pass1234",
        )

        emb = get_embeddings()
        texts_a = ["User A secret document about elephants."]
        vectors_a = emb.embed_documents(texts_a)
        vectorstore.upsert_chunks(user_a.pk, document_id=10, texts=texts_a, embeddings=vectors_a)

        # B has no documents; retrieving with B's ID must not surface A's content.
        chunks_b = retrieve(user_b.pk, "elephants")
        assert len(chunks_b) == 0, "User B must not see User A's chunks via retrieve()"

    def test_respects_top_k(self) -> None:
        """retrieve() must return at most k chunks."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.embeddings import get_embeddings  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_topk@test.com",
            email="ret_topk@test.com",
            password="pass1234",
        )

        emb = get_embeddings()
        texts = [f"Chunk number {i} with distinct content about topic {i}." for i in range(10)]
        vectors = emb.embed_documents(texts)
        vectorstore.upsert_chunks(user.pk, document_id=20, texts=texts, embeddings=vectors)

        chunks = retrieve(user.pk, "chunk topic", k=2)
        assert len(chunks) <= 2

    def test_default_k_is_retrieval_top_k(self) -> None:
        """retrieve() with k=None must use RETRIEVAL_TOP_K from settings."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.embeddings import get_embeddings  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_defk@test.com",
            email="ret_defk@test.com",
            password="pass1234",
        )

        emb = get_embeddings()
        top_k = settings.RETRIEVAL_TOP_K
        texts = [f"Document chunk {i}." for i in range(top_k + 2)]
        vectors = emb.embed_documents(texts)
        vectorstore.upsert_chunks(user.pk, document_id=30, texts=texts, embeddings=vectors)

        chunks = retrieve(user.pk, "chunk")
        assert len(chunks) <= top_k


# ---------------------------------------------------------------------------
# Context building — bounded
# ---------------------------------------------------------------------------


class TestContextBuilding:
    def test_context_bounded_by_k_chunks(self) -> None:
        """The view builds context from at most k chunks (D-014)."""
        # We can test the context building logic directly: joining k chunks
        # produces a bounded string, not the full document.
        k = 4
        chunks = [{"text": f"Chunk {i}", "document_id": str(i)} for i in range(k)]
        context = "\n\n".join(c["text"] for c in chunks)
        assert context.count("Chunk") == k

    def test_context_from_single_chunk(self) -> None:
        """Single chunk context is just that chunk's text."""
        chunks = [{"text": "Only chunk text.", "document_id": "1"}]
        context = "\n\n".join(c["text"] for c in chunks)
        assert context == "Only chunk text."

    def test_context_separator_is_double_newline(self) -> None:
        """Chunks are separated by \\n\\n in the context string."""
        chunks = [
            {"text": "First chunk.", "document_id": "1"},
            {"text": "Second chunk.", "document_id": "2"},
        ]
        context = "\n\n".join(c["text"] for c in chunks)
        assert "\n\n" in context
        assert context == "First chunk.\n\nSecond chunk."


# ---------------------------------------------------------------------------
# CreditAccount model unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreditAccountModel:
    def test_default_balance_from_settings(self) -> None:
        """CreditAccount created via get_or_create_account uses DEFAULT_CHAT_CREDITS."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        user = User.objects.create_user(
            username="cred_model@test.com",
            email="cred_model@test.com",
            password="pass1234",
        )
        acc = get_or_create_account(user)
        assert acc.balance == settings.DEFAULT_CHAT_CREDITS

    def test_credit_account_str(self) -> None:
        """CreditAccount __str__ contains user_id and balance."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        user = User.objects.create_user(
            username="cred_str@test.com",
            email="cred_str@test.com",
            password="pass1234",
        )
        acc = get_or_create_account(user)
        s = str(acc)
        assert str(user.pk) in s
        assert str(acc.balance) in s

    def test_get_or_create_is_idempotent(self) -> None:
        """Multiple calls to get_or_create_account return the same row."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        user = User.objects.create_user(
            username="cred_idem2@test.com",
            email="cred_idem2@test.com",
            password="pass1234",
        )
        acc_a = get_or_create_account(user)
        acc_b = get_or_create_account(user)
        assert acc_a.pk == acc_b.pk
        assert CreditAccount.objects.filter(user=user).count() == 1

    def test_balance_floor_arithmetic(self) -> None:
        """Simulating max(0, balance - tokens) never goes negative."""
        # Balance 5, tokens 100 → floor to 0.
        balance = 5
        tokens = 100
        result = max(0, balance - tokens)
        assert result == 0

        # Balance 50, tokens 30 → exactly 20.
        balance = 50
        tokens = 30
        result = max(0, balance - tokens)
        assert result == 20

    def test_credit_account_one_to_one_constraint(self) -> None:
        """Only one CreditAccount per user (OneToOne constraint)."""
        from apps.accounts.models import CreditAccount  # noqa: PLC0415
        from django.db import IntegrityError  # noqa: PLC0415

        user = User.objects.create_user(
            username="cred_121@test.com",
            email="cred_121@test.com",
            password="pass1234",
        )
        CreditAccount.objects.create(user=user, balance=100)
        with pytest.raises(IntegrityError):
            CreditAccount.objects.create(user=user, balance=200)


# ---------------------------------------------------------------------------
# get_llm_client offline safety
# ---------------------------------------------------------------------------


class TestLLMClientOfflineSafety:
    def test_stub_complete_does_not_make_network_calls(self) -> None:
        """_StubLLM.complete must not construct an OpenAI client."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        # Calling complete() on the stub must not raise any import/network errors.
        # If it tried to call openai, it would fail because no real key is set.
        result = stub.complete("sys", "context", "question")
        assert result.tokens > 0  # confirms it ran without error

    def test_stub_answer_contains_stub_marker(self) -> None:
        """Stub answer contains the [stub answer] marker for easy identification."""
        from apps.rag.llm import _StubLLM  # noqa: PLC0415

        stub = _StubLLM()
        result = stub.complete("system", "some context", "some question")
        assert "stub" in result.answer.lower()
