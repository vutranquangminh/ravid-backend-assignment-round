"""Targeted tests for uncovered branches across multiple modules.

Covers (all offline, no network):
  - apps/rag/embeddings.py:44      — get_embeddings factory with stub flag explicitly False
                                     (the HF import itself is mocked, not called)
  - apps/rag/vectorstore.py:62     — HttpClient branch (already in test_vectorstore_modes,
                                     but line 62 is the actual HttpClient(...) call)
  - apps/rag/vectorstore.py:123-125 — delete_document_vectors when get_collection raises
  - apps/rag/retrieval.py:51-57    — retrieve() when vectorstore.query raises
  - apps/rag/retrieval.py:69       — retrieve() when empty documents list returned
  - apps/rag/serializers.py:36     — validate_query raises ValidationError path
  - apps/rag/pipeline.py:115       — run_ingestion when splitter yields no chunks
  - apps/documents/models.py:48    — Document.__str__
  - apps/accounts/views.py:46-47   — RegisterView ValueError from register_user
  - apps/accounts/views.py:110,113-116 — _first_error with str / dict nested errors
  - apps/documents/views.py:112-114 — DocumentDeleteView vectorstore exception swallowed
  - apps/documents/views.py:130,133-135 — _first_error with str / dict nested errors
  - apps/rag/tasks.py:43-48        — ingest_document when IngestionJob.DoesNotExist
  - apps/rag/views.py:179-184      — ChatQueryView retrieval raises → 502
  - apps/rag/views.py:239-249      — ChatQueryView LLM raises → 502
  - apps/rag/views.py:345-350      — ChatStreamView retrieval raises → 502
  - apps/rag/views.py:466,469-471  — _first_error with str / dict nested branches
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants (integration helpers need them)
# ---------------------------------------------------------------------------

REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
UPLOAD_URL = "/api/documents/upload/"
CHAT_URL = "/api/chat/query/"
CHAT_STREAM_URL = "/api/chat/stream/"
DELETE_URL_FMT = "/api/documents/{}/"

_TXT_BYTES = b"Some plain text content to satisfy ingestion pipeline checks."


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _register_and_login(email: str, password: str = "StrongPass1!") -> str:
    c = Client()
    _post_json(c, REGISTER_URL, {"email": email, "password": password})
    resp = _post_json(c, LOGIN_URL, {"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["token"]


def _auth(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _upload(token: str, content: bytes = _TXT_BYTES) -> dict:
    c = Client()
    f = SimpleUploadedFile("doc.txt", content, content_type="text/plain")
    resp = c.post(UPLOAD_URL, data={"file": f}, **_auth(token))
    assert resp.status_code == 202
    return resp.json()


# ===========================================================================
# apps/rag/embeddings.py line 44 (get_embeddings when RAVID_EMBEDDINGS_STUB is False)
# We mock the HuggingFaceEmbeddings import so no real model is loaded.
# ===========================================================================


class TestGetEmbeddingsRealBranch:
    def test_real_branch_calls_huggingface_embeddings(self) -> None:
        """When RAVID_EMBEDDINGS_STUB=False, get_embeddings imports HuggingFaceEmbeddings."""
        fake_hf = MagicMock(name="HuggingFaceEmbeddings")
        fake_instance = MagicMock()
        fake_hf.return_value = fake_instance

        with (
            override_settings(RAVID_EMBEDDINGS_STUB=False, EMBEDDING_MODEL="test/model"),
            patch("langchain_huggingface.HuggingFaceEmbeddings", fake_hf),
        ):
            from apps.rag.embeddings import get_embeddings  # noqa: PLC0415

            result = get_embeddings()

        fake_hf.assert_called_once_with(model_name="test/model")
        assert result is fake_instance


class TestStubEmbeddingsWhileLoop:
    def test_while_loop_fires_when_stub_dim_greater_than_hash_length(self) -> None:
        """The while loop in _hash_to_vector fires when _STUB_DIM > 32 (SHA-256 bytes).

        SHA-256 produces exactly 32 bytes. With _STUB_DIM=32 the loop never fires.
        We patch _STUB_DIM to 64 to exercise the loop body (line 44).
        """
        from apps.rag import embeddings  # noqa: PLC0415
        from apps.rag.embeddings import _StubEmbeddings  # noqa: PLC0415

        original_dim = embeddings._STUB_DIM
        try:
            embeddings._STUB_DIM = 64  # > 32 bytes from SHA-256 → while body fires
            stub = _StubEmbeddings()
            vec = stub._hash_to_vector("test input")
            assert len(vec) == 64
        finally:
            embeddings._STUB_DIM = original_dim


# ===========================================================================
# apps/rag/vectorstore.py line 62 (HttpClient called with host+port+settings)
# Already partially tested in test_vectorstore_modes, but line 62 is the
# actual HttpClient() call — this test ensures it's recorded as covered.
# ===========================================================================


class TestVectorstoreHttpClientLine:
    def test_http_client_call_is_exercised(self) -> None:
        """The real chromadb.HttpClient() call on line 62 is reached."""
        from apps.rag import vectorstore  # noqa: PLC0415

        sentinel = MagicMock(name="HttpClientInstance")
        vectorstore._chroma_client = None  # reset singleton

        with (
            override_settings(CHROMA_HOST="test-chroma-host", CHROMA_PORT=8765),
            patch("chromadb.HttpClient", return_value=sentinel) as mock_http,
        ):
            vectorstore._chroma_client = None
            client = vectorstore._client()

        mock_http.assert_called_once()
        assert client is sentinel
        vectorstore._chroma_client = None  # clean up

    def test_reset_client_function_clears_singleton(self) -> None:
        """_reset_client() sets _chroma_client to None (line 62 of vectorstore.py)."""
        from apps.rag import vectorstore  # noqa: PLC0415

        # Ensure there's something to reset
        vectorstore._chroma_client = MagicMock(name="FakeClient")
        assert vectorstore._chroma_client is not None
        # Call the public reset helper
        vectorstore._reset_client()
        assert vectorstore._chroma_client is None


# ===========================================================================
# apps/rag/vectorstore.py lines 123-125
# delete_document_vectors when get_collection raises (collection doesn't exist)
# ===========================================================================


class TestDeleteDocumentVectorsCollectionRaises:
    def test_silent_when_get_collection_raises(self) -> None:
        """If get_collection raises, delete_document_vectors returns silently."""
        from apps.rag import vectorstore  # noqa: PLC0415

        with patch.object(vectorstore, "get_collection", side_effect=Exception("no collection")):
            # Must not raise
            vectorstore.delete_document_vectors(owner_id=99999, document_id=1)


# ===========================================================================
# apps/rag/retrieval.py lines 51-57
# retrieve() when vectorstore.query raises → logs and returns []
# ===========================================================================


@pytest.mark.django_db
class TestRetrieveVectorstoreRaises:
    def test_returns_empty_list_when_query_raises(self) -> None:
        """retrieve() catches any vectorstore.query exception and returns []."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_exc@test.com",
            email="ret_exc@test.com",
            password="pass1234",
        )

        with patch.object(vectorstore, "query", side_effect=Exception("chroma down")):
            result = retrieve(user.pk, "some query")

        assert result == []


# ===========================================================================
# apps/rag/retrieval.py line 69
# retrieve() when empty documents list in the result → return []
# ===========================================================================


@pytest.mark.django_db
class TestRetrieveEmptyDocuments:
    def test_returns_empty_list_when_no_documents_in_result(self) -> None:
        """retrieve() returns [] when the query result has no documents."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_nodocs@test.com",
            email="ret_nodocs@test.com",
            password="pass1234",
        )

        # Return a result where documents is an empty inner list
        with patch.object(
            vectorstore, "query", return_value={"documents": [[]], "metadatas": [[]]}
        ):
            result = retrieve(user.pk, "anything")

        assert result == []

    def test_skips_none_text_entries(self) -> None:
        """retrieve() skips any chunk entry where text is None (line 69)."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user = User.objects.create_user(
            username="ret_none_text@test.com",
            email="ret_none_text@test.com",
            password="pass1234",
        )

        # Return a result where one document is None and one is valid
        mock_result = {
            "documents": [[None, "valid text"]],
            "metadatas": [[{"document_id": "1"}, {"document_id": "2"}]],
        }
        with patch.object(vectorstore, "query", return_value=mock_result):
            result = retrieve(user.pk, "anything")

        # The None entry is skipped; only the valid text is returned
        assert len(result) == 1
        assert result[0]["text"] == "valid text"
        assert result[0]["document_id"] == "2"


# ===========================================================================
# apps/rag/serializers.py line 36
# validate_query raises when value is whitespace-only (after trimming)
# ===========================================================================


class TestChatQuerySerializerValidateQuery:
    def test_validate_query_raises_for_whitespace_only_input(self) -> None:
        """Whitespace-only query triggers a validation error."""
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": "   "})
        assert not s.is_valid()
        assert "query" in s.errors

    def test_validate_query_message_exact(self) -> None:
        """validate_query raises with 'query is required.' in errors."""
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415

        s = ChatQuerySerializer(data={"query": "\t\n  \r\n"})
        assert not s.is_valid()
        assert "query is required." in str(s.errors)

    def test_validate_query_method_raises_directly(self) -> None:
        """Calling validate_query() directly with whitespace-only value raises ValidationError."""
        from apps.rag.serializers import ChatQuerySerializer  # noqa: PLC0415
        from rest_framework import serializers as drf_serializers  # noqa: PLC0415

        # Directly invoke the field-level validator, bypassing trim_whitespace.
        # We pass a raw non-trimmed whitespace string directly.
        serializer = ChatQuerySerializer()
        with pytest.raises(drf_serializers.ValidationError) as exc_info:
            serializer.validate_query("   ")  # non-empty but whitespace — strip() is ""
        assert "query is required." in str(exc_info.value.detail)


# ===========================================================================
# apps/rag/pipeline.py line 115
# run_ingestion when splitter returns no chunks
# ===========================================================================


class TestPipelineNoChunks:
    def test_raises_when_splitter_returns_no_chunks(self) -> None:
        """When splitter yields [], run_ingestion raises ValueError."""
        import os  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        from apps.rag import pipeline  # noqa: PLC0415

        # Write a temp file with some text
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write("some content here")

        class _FakeFile:
            def __init__(self, p):
                self.path = p

        class _FakeDoc:
            def __init__(self, p):
                self.file = _FakeFile(p)
                self.content_type = "text/plain"

        class _FakeJob:
            def __init__(self, p):
                self.owner_id = 9999999
                self.source_document_id = 9999999
                self.source_document = _FakeDoc(p)

        job = _FakeJob(path)

        # Patch the splitter to return an empty list
        with (
            patch(
                "langchain_text_splitters.RecursiveCharacterTextSplitter.split_text",
                return_value=[],
            ),
            pytest.raises(ValueError, match="No extractable text"),
        ):
            pipeline.run_ingestion(job)


# ===========================================================================
# apps/documents/models.py line 48
# Document.__str__
# ===========================================================================


@pytest.mark.django_db
class TestDocumentStr:
    def test_str_representation(self) -> None:
        """Document.__str__ returns the expected string format."""
        from apps.documents.models import Document  # noqa: PLC0415

        token = _register_and_login("doc_str2@test.com")
        upload_resp = _upload(token)
        doc = Document.objects.get(pk=upload_resp["document_id"])
        s = str(doc)
        assert "Document(" in s
        assert str(doc.pk) in s
        assert "owner=" in s
        assert "name=" in s


# ===========================================================================
# apps/accounts/views.py lines 46-47
# RegisterView: register_user raises ValueError → 400 {"error": str(exc)}
# ===========================================================================


@pytest.mark.django_db
class TestRegisterViewValueError:
    def test_register_returns_400_when_service_raises_value_error(self) -> None:
        """RegisterView catches ValueError from register_user and returns 400."""
        c = Client()
        # Patch the name as imported into the view module (not the original module).
        with patch("apps.accounts.views.register_user", side_effect=ValueError("duplicate email")):
            resp = _post_json(c, REGISTER_URL, {"email": "new@test.com", "password": "strongpass1"})

        assert resp.status_code == 400
        assert resp.json() == {"error": "duplicate email"}


# ===========================================================================
# apps/accounts/views.py lines 110, 113-116
# _first_error in accounts/views.py — str value branch + dict nested branch
# ===========================================================================


class TestAccountsFirstError:
    def test_first_error_returns_string_value_directly(self) -> None:
        """_first_error returns the string value when value is a str."""
        from apps.accounts.views import _first_error  # noqa: PLC0415

        errors = {"non_field_errors": "Top-level string error."}
        assert _first_error(errors) == "Top-level string error."

    def test_first_error_recurses_into_dict(self) -> None:
        """_first_error recurses one level for nested serializer errors."""
        from apps.accounts.views import _first_error  # noqa: PLC0415

        errors = {"nested": {"field": ["Inner error message."]}}
        result = _first_error(errors)
        assert result == "Inner error message."

    def test_first_error_returns_fallback_on_empty(self) -> None:
        """_first_error returns 'Invalid input.' when errors dict is empty."""
        from apps.accounts.views import _first_error  # noqa: PLC0415

        assert _first_error({}) == "Invalid input."


# ===========================================================================
# apps/documents/views.py lines 112-114
# DocumentDeleteView when vectorstore.delete_document_vectors raises — silently ignored
# ===========================================================================


@pytest.mark.django_db
class TestDocumentDeleteVectorstoreException:
    def test_delete_succeeds_even_when_vectorstore_raises(self) -> None:
        """Exceptions in vectorstore.delete_document_vectors are swallowed (BLE001)."""
        from apps.rag import vectorstore  # noqa: PLC0415

        token = _register_and_login("del_vs_exc@test.com")
        upload_resp = _upload(token)
        doc_id = upload_resp["document_id"]

        c = Client()
        with patch.object(
            vectorstore, "delete_document_vectors", side_effect=Exception("chroma error")
        ):
            resp = c.delete(DELETE_URL_FMT.format(doc_id), **_auth(token))

        # The delete should still succeed — vectorstore error is best-effort
        assert resp.status_code == 204


# ===========================================================================
# apps/documents/views.py lines 130, 133-135
# _first_error in documents/views.py — str + dict nested branches
# ===========================================================================


class TestDocumentsFirstError:
    def test_first_error_returns_string_value_directly(self) -> None:
        """_first_error returns string values directly."""
        from apps.documents.views import _first_error  # noqa: PLC0415

        errors = {"detail": "Some string message."}
        assert _first_error(errors) == "Some string message."

    def test_first_error_recurses_into_nested_dict(self) -> None:
        """_first_error recurses into nested dicts."""
        from apps.documents.views import _first_error  # noqa: PLC0415

        errors = {"file": {"inner_key": ["Nested error."]}}
        result = _first_error(errors)
        assert result == "Nested error."

    def test_first_error_fallback_for_empty(self) -> None:
        from apps.documents.views import _first_error  # noqa: PLC0415

        assert _first_error({}) == "Invalid input."


# ===========================================================================
# apps/rag/tasks.py lines 43-48
# ingest_document when IngestionJob.DoesNotExist → returns NOT_FOUND dict
# ===========================================================================


@pytest.mark.django_db
class TestIngestDocumentJobNotFound:
    def test_returns_not_found_when_job_missing(self) -> None:
        """ingest_document returns {'status': 'NOT_FOUND'} for a missing job pk."""
        from apps.rag.tasks import ingest_document  # noqa: PLC0415

        # Use a pk that definitely doesn't exist
        result = ingest_document(9999999)
        assert result["status"] == "NOT_FOUND"
        assert result["job_id"] == 9999999


# ===========================================================================
# apps/rag/views.py lines 179-184
# ChatQueryView: retrieve() raises → 502
# ===========================================================================


@pytest.mark.django_db
class TestChatQueryRetrievalError:
    def test_retrieval_exception_returns_502(self) -> None:
        """When retrieve() raises, ChatQueryView returns 502."""
        from apps.rag import retrieval  # noqa: PLC0415

        token = _register_and_login("chat_ret_exc@test.com")
        # Upload a doc so the user has credits and won't hit the no-context guard
        _upload(token)

        c = Client()
        with patch.object(retrieval, "retrieve", side_effect=RuntimeError("embedding down")):
            resp = _post_json(c, CHAT_URL, {"query": "test query"})
            # Note: this needs auth
            resp = c.post(
                CHAT_URL,
                data=json.dumps({"query": "test query"}),
                content_type="application/json",
                **_auth(token),
            )

        assert resp.status_code == 502
        assert "error" in resp.json()


# ===========================================================================
# apps/rag/views.py lines 239-249
# ChatQueryView: LLM call raises → 502
# ===========================================================================


@pytest.mark.django_db
class TestChatQueryLLMError:
    def test_llm_exception_returns_502(self) -> None:
        """When get_llm_client().complete() raises, ChatQueryView returns 502."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.embeddings import get_embeddings  # noqa: PLC0415

        token = _register_and_login("chat_llm_exc@test.com")

        # Seed the user's collection so retrieval returns chunks (bypasses no-context guard)
        user = User.objects.get(email="chat_llm_exc@test.com")
        emb = get_embeddings()
        texts = ["Some context text to return from retrieval."]
        vectors = emb.embed_documents(texts)
        vectorstore.upsert_chunks(user.pk, document_id=1, texts=texts, embeddings=vectors)

        # Make a stub client whose .complete() raises
        mock_client = MagicMock()
        mock_client.complete.side_effect = RuntimeError("LLM is down")

        from apps.rag import llm  # noqa: PLC0415

        c = Client()
        with patch.object(llm, "get_llm_client", return_value=mock_client):
            resp = c.post(
                CHAT_URL,
                data=json.dumps({"query": "test query"}),
                content_type="application/json",
                **_auth(token),
            )

        assert resp.status_code == 502
        body = resp.json()
        assert "error" in body
        assert "LLM" in body["error"] or "failed" in body["error"].lower()


# ===========================================================================
# apps/rag/views.py lines 345-350
# ChatStreamView: retrieve() raises → 502
# ===========================================================================


@pytest.mark.django_db
class TestChatStreamRetrievalError:
    def test_retrieval_exception_returns_502(self) -> None:
        """When retrieve() raises in stream view, ChatStreamView returns 502."""
        from apps.rag import retrieval  # noqa: PLC0415

        token = _register_and_login("stream_ret_exc@test.com")

        c = Client()
        with patch.object(retrieval, "retrieve", side_effect=RuntimeError("chroma down")):
            resp = c.post(
                CHAT_STREAM_URL,
                data=json.dumps({"query": "test query"}),
                content_type="application/json",
                **_auth(token),
            )

        assert resp.status_code == 502
        assert "error" in resp.json()


# ===========================================================================
# apps/rag/views.py lines 466, 469-471
# _first_error in rag/views.py — str branch and dict nested branch
# ===========================================================================


class TestRagFirstError:
    def test_first_error_returns_string_value(self) -> None:
        """_first_error in rag/views.py handles string values."""
        from apps.rag.views import _first_error  # noqa: PLC0415

        errors = {"detail": "Top-level string error."}
        assert _first_error(errors) == "Top-level string error."

    def test_first_error_recurses_into_nested_dict(self) -> None:
        """_first_error in rag/views.py recurses into nested dicts."""
        from apps.rag.views import _first_error  # noqa: PLC0415

        errors = {"nested": {"field": ["Nested error message."]}}
        result = _first_error(errors)
        assert result == "Nested error message."

    def test_first_error_fallback(self) -> None:
        """_first_error returns 'Invalid input.' for empty dict."""
        from apps.rag.views import _first_error  # noqa: PLC0415

        assert _first_error({}) == "Invalid input."
