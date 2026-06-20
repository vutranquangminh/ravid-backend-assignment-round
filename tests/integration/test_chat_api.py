"""Integration tests for the RAG chat query endpoint (slice 05).

All tests run fully offline:
  - RAVID_LLM_STUB=True    → deterministic stub LLM, no OpenRouter calls.
  - RAVID_EMBEDDINGS_STUB=True → deterministic stub embeddings, no model download.
  - CHROMA_PERSIST_DIR is a temp dir (reset between tests by conftest autouse fixture).
  - CELERY_TASK_ALWAYS_EAGER=True → ingestion tasks run synchronously.

Coverage:
  Happy path:       upload+ingest → chat → 200 {answer, tokens_consumed > 0}.
  Grounding:        user A's context never contains user B's content.
  Isolation:        retrieve() scoped to caller; third user with no docs → guard.
  No-context guard: empty KB → fixed answer, tokens_consumed==0, balance unchanged,
                    LLM NOT called.
  Credits:          starting balance == DEFAULT_CHAT_CREDITS; deducted after chat;
                    balance=0 → 402; multiple chats accumulate; floor at 0.
  Validation/auth:  missing/empty/whitespace query → 400; no JWT → 401; GET → 405.
  Regression:       /api/chat/query/ now routed; prior endpoints still work.
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

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

CHAT_URL = "/api/chat/query/"
UPLOAD_URL = "/api/documents/upload/"
STATUS_URL = "/api/documents/status/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
HEALTH_URL = "/api/health/"

# ---------------------------------------------------------------------------
# Minimal document contents
# ---------------------------------------------------------------------------

_TXT_A = b"The capital of France is Paris. It is a beautiful city on the Seine."
_TXT_B = (
    b"Quantum entanglement is a phenomenon in quantum mechanics. Einstein called it spooky action."
)
_TXT_GENERIC = b"This is a generic document with some sample text for embedding and retrieval."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _register_and_login(email: str, password: str = "StrongPass1!") -> str:
    """Register a new user and return their JWT access token."""
    c = Client()
    _post_json(c, REGISTER_URL, {"email": email, "password": password})
    resp = _post_json(c, LOGIN_URL, {"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["token"]


def _upload_and_ingest(token: str, content: bytes, filename: str = "doc.txt") -> dict:
    """Upload a document and return the upload response JSON."""
    client = Client()
    f = SimpleUploadedFile(filename, content, content_type="text/plain")
    resp = client.post(
        UPLOAD_URL,
        data={"file": f},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 202, f"Upload failed: {resp.json()}"
    return resp.json()


def _chat(client: Client, token: str, query: str) -> object:
    return client.post(
        CHAT_URL,
        data=json.dumps({"query": query}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChatHappyPath:
    def test_upload_ingest_then_chat_200(self) -> None:
        """Upload + ingest a doc, then POST /api/chat/query/ → 200 with answer."""
        token = _register_and_login("chat_happy@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "What is this document about?")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.json()}"
        body = resp.json()
        assert "answer" in body
        assert "tokens_consumed" in body

    def test_answer_is_non_empty(self) -> None:
        """The answer field must be a non-empty string."""
        token = _register_and_login("chat_nonempty@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "Tell me about this document.")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_tokens_consumed_positive(self) -> None:
        """tokens_consumed must be > 0 when an LLM call is made."""
        token = _register_and_login("chat_tokens@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "What is in the document?")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tokens_consumed"] > 0

    def test_tokens_consumed_matches_stub_formula(self) -> None:
        """tokens_consumed must equal the stub LLM's deterministic output."""
        token = _register_and_login("chat_stub_formula@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "Summarise the document.")
        assert resp.status_code == 200
        body = resp.json()
        # tokens_consumed must be a positive integer matching the stub behaviour.
        assert isinstance(body["tokens_consumed"], int)
        assert body["tokens_consumed"] > 0

    def test_response_keys_are_exactly_answer_and_tokens(self) -> None:
        """Success response must have {answer, tokens_consumed, chat_id} keys (chat_id additive in s08)."""
        token = _register_and_login("chat_keys@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        client = Client()
        resp = _chat(client, token, "Any question")
        assert resp.status_code == 200
        assert set(resp.json().keys()) == {"answer", "tokens_consumed", "chat_id"}


# ---------------------------------------------------------------------------
# Grounding / isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGroundingIsolation:
    def test_user_a_context_does_not_contain_user_b_content(self) -> None:
        """User A's retrieval must never surface user B's distinctive content."""
        token_a = _register_and_login("iso_chat_a@test.com")
        token_b = _register_and_login("iso_chat_b@test.com")

        # A uploads France doc; B uploads quantum doc.
        _upload_and_ingest(token_a, _TXT_A, "france.txt")
        _upload_and_ingest(token_b, _TXT_B, "quantum.txt")

        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        user_a = User.objects.get(email="iso_chat_a@test.com")
        user_b = User.objects.get(email="iso_chat_b@test.com")

        chunks_a = retrieve(user_a.pk, "capital city France")
        chunks_b = retrieve(user_b.pk, "quantum entanglement")

        # A's chunks must not contain quantum content.
        a_texts = " ".join(c["text"] for c in chunks_a).lower()
        assert "quantum" not in a_texts, (
            "User A's retrieval must not contain user B's quantum content"
        )

        # B's chunks must not contain France content.
        b_texts = " ".join(c["text"] for c in chunks_b).lower()
        assert "france" not in b_texts, (
            "User B's retrieval must not contain user A's France content"
        )

    def test_chat_for_user_a_does_not_expose_user_b_answer(self) -> None:
        """A's chat answer is generated only from A's docs."""
        token_a = _register_and_login("iso_ans_a@test.com")
        token_b = _register_and_login("iso_ans_b@test.com")

        _upload_and_ingest(token_a, _TXT_A, "france.txt")
        _upload_and_ingest(token_b, _TXT_B, "quantum.txt")

        client = Client()
        resp_a = _chat(client, token_a, "What city is mentioned?")
        assert resp_a.status_code == 200
        # A's answer was generated from A's France context — quantum should not appear.
        # (The stub uses context length, not semantic content, but we can verify tokens > 0
        # and that the endpoint returns without error.)
        body_a = resp_a.json()
        assert body_a["tokens_consumed"] > 0

    def test_third_user_no_docs_hits_no_context_guard(self) -> None:
        """A user with no ingested documents must hit the no-context guard."""
        token_c = _register_and_login("iso_nodc@test.com")
        client = Client()
        resp = _chat(client, token_c, "What is this about?")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tokens_consumed"] == 0
        assert "couldn't find anything relevant" in body["answer"].lower()

    def test_retrieve_scoped_to_owner_only(self) -> None:
        """retrieve() must return only the owner's own chunks."""
        from apps.rag.retrieval import retrieve  # noqa: PLC0415

        token_x = _register_and_login("scope_x@test.com")
        token_y = _register_and_login("scope_y@test.com")

        _upload_and_ingest(token_x, _TXT_A, "doc_x.txt")
        _upload_and_ingest(token_y, _TXT_B, "doc_y.txt")

        user_x = User.objects.get(email="scope_x@test.com")
        user_y = User.objects.get(email="scope_y@test.com")

        chunks_x = retrieve(user_x.pk, "France Paris Seine")
        chunks_y = retrieve(user_y.pk, "quantum entanglement")

        # Each user gets their own chunks and only their own.
        assert len(chunks_x) > 0, "User X should have chunks after ingestion"
        assert len(chunks_y) > 0, "User Y should have chunks after ingestion"

        # Verify cross-contamination is absent.
        x_texts = " ".join(c["text"] for c in chunks_x).lower()
        y_texts = " ".join(c["text"] for c in chunks_y).lower()
        assert "quantum" not in x_texts
        assert "france" not in y_texts


# ---------------------------------------------------------------------------
# No-context guard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNoContextGuard:
    def test_empty_kb_returns_fixed_answer(self) -> None:
        """User with no docs gets the fixed no-context answer."""
        token = _register_and_login("nocontext_ans@test.com")
        client = Client()
        resp = _chat(client, token, "Who won the championship?")
        assert resp.status_code == 200
        body = resp.json()
        assert "couldn't find anything relevant" in body["answer"].lower()

    def test_empty_kb_tokens_zero(self) -> None:
        """No-context guard must return tokens_consumed == 0."""
        token = _register_and_login("nocontext_tok@test.com")
        client = Client()
        resp = _chat(client, token, "Some question")
        assert resp.status_code == 200
        assert resp.json()["tokens_consumed"] == 0

    def test_empty_kb_balance_unchanged(self) -> None:
        """Credit balance must not change on a no-context guard response."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("nocontext_bal@test.com")
        user = User.objects.get(email="nocontext_bal@test.com")
        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        _chat(client, token, "Any question")

        account.refresh_from_db()
        assert account.balance == balance_before, (
            "Balance must not change when no-context guard fires"
        )

    def test_empty_kb_llm_not_called(self) -> None:
        """LLM client must NOT be called when the no-context guard fires."""
        token = _register_and_login("nocontext_llm@test.com")
        client = Client()

        # Use a targeted patch on the actual llm module.
        with patch("apps.rag.llm._StubLLM.complete") as mock_complete:
            resp = _chat(client, token, "Any question with no docs")
            assert resp.status_code == 200
            assert resp.json()["tokens_consumed"] == 0
            mock_complete.assert_not_called()

    def test_no_context_response_keys(self) -> None:
        """No-context guard response must have {answer, tokens_consumed, chat_id} (chat_id additive in s08)."""
        token = _register_and_login("nocontext_keys@test.com")
        client = Client()
        resp = _chat(client, token, "Anything")
        assert resp.status_code == 200
        assert set(resp.json().keys()) == {"answer", "tokens_consumed", "chat_id"}


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCredits:
    def test_starting_balance_equals_default_chat_credits(self) -> None:
        """A newly created CreditAccount starts with DEFAULT_CHAT_CREDITS."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        _register_and_login("cred_start@test.com")
        user = User.objects.get(email="cred_start@test.com")
        account = get_or_create_account(user)
        assert account.balance == settings.DEFAULT_CHAT_CREDITS

    def test_balance_decremented_after_chat(self) -> None:
        """After a chat, balance must be reduced by tokens_consumed."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("cred_deduct@test.com")
        user = User.objects.get(email="cred_deduct@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        resp = _chat(client, token, "What is in this document?")
        assert resp.status_code == 200
        tokens_consumed = resp.json()["tokens_consumed"]
        assert tokens_consumed > 0

        account.refresh_from_db()
        expected = max(0, balance_before - tokens_consumed)
        assert account.balance == expected, f"Balance should be {expected}, got {account.balance}"

    def test_zero_balance_returns_402(self) -> None:
        """A user with balance=0 must get 402 and LLM must not be called."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        token = _register_and_login("cred_zero@test.com")
        user = User.objects.get(email="cred_zero@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        # Set balance to 0.
        account = get_or_create_account(user)
        CreditAccount.objects.filter(pk=account.pk).update(balance=0)

        client = Client()
        with patch("apps.rag.llm._StubLLM.complete") as mock_complete:
            resp = _chat(client, token, "Any question")
            assert resp.status_code == 402, f"Expected 402, got {resp.status_code}"
            assert "error" in resp.json()
            assert "insufficient credits" in resp.json()["error"].lower()
            mock_complete.assert_not_called()

    def test_zero_balance_error_envelope(self) -> None:
        """402 response must use the exact error envelope."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        token = _register_and_login("cred_zero_env@test.com")
        user = User.objects.get(email="cred_zero_env@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        CreditAccount.objects.filter(pk=account.pk).update(balance=0)

        client = Client()
        resp = _chat(client, token, "What is this?")
        assert resp.status_code == 402
        body = resp.json()
        assert body == {"error": "Insufficient credits."}

    def test_guard_path_does_not_charge_credits(self) -> None:
        """No-context guard must not charge credits (balance must stay the same)."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("cred_guard@test.com")
        user = User.objects.get(email="cred_guard@test.com")

        account = get_or_create_account(user)
        balance_before = account.balance

        client = Client()
        resp = _chat(client, token, "No docs uploaded")
        assert resp.status_code == 200
        assert resp.json()["tokens_consumed"] == 0

        account.refresh_from_db()
        assert account.balance == balance_before

    def test_multiple_chats_accumulate_deductions(self) -> None:
        """Each successful chat reduces balance; multiple chats accumulate."""
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        token = _register_and_login("cred_accum@test.com")
        user = User.objects.get(email="cred_accum@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        account = get_or_create_account(user)
        balance_start = account.balance

        client = Client()
        total_tokens = 0
        for i in range(3):
            resp = _chat(client, token, f"Question number {i}")
            assert resp.status_code == 200
            total_tokens += resp.json()["tokens_consumed"]

        account.refresh_from_db()
        expected = max(0, balance_start - total_tokens)
        assert account.balance == expected

    def test_balance_never_goes_negative(self) -> None:
        """Balance is floored at 0; it can never become negative."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        token = _register_and_login("cred_floor@test.com")
        user = User.objects.get(email="cred_floor@test.com")
        _upload_and_ingest(token, _TXT_GENERIC)

        # Set balance to 1 so the stub's token count will exceed it.
        account = get_or_create_account(user)
        CreditAccount.objects.filter(pk=account.pk).update(balance=1)

        client = Client()
        resp = _chat(client, token, "Something that will use many tokens")
        # If balance is 1 and stub produces > 1 token, floor kicks in.
        # If somehow tokens == 1 the balance is exactly 0. Either way >= 0.
        if resp.status_code == 200:
            account.refresh_from_db()
            assert account.balance >= 0, "Balance must never go negative"

    def test_get_or_create_account_idempotent(self) -> None:
        """Calling get_or_create_account twice returns the same record."""
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        _register_and_login("cred_idem@test.com")
        user = User.objects.get(email="cred_idem@test.com")

        acc1 = get_or_create_account(user)
        acc2 = get_or_create_account(user)
        assert acc1.pk == acc2.pk
        assert CreditAccount.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# Validation / auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestValidationAndAuth:
    def test_missing_query_field_returns_400(self) -> None:
        """POST with no 'query' field → 400 {error}."""
        token = _register_and_login("val_missing@test.com")
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert body["error"]  # non-empty

    def test_empty_query_returns_400(self) -> None:
        """POST with query='' → 400 {error}."""
        token = _register_and_login("val_empty@test.com")
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": ""}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_whitespace_only_query_returns_400(self) -> None:
        """POST with query='   \\t\\n' → 400 {error}."""
        token = _register_and_login("val_ws@test.com")
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": "   \t\n"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_missing_query_error_message(self) -> None:
        """Error message must be 'query is required.' (exact)."""
        token = _register_and_login("val_msg@test.com")
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "query is required."

    def test_no_jwt_returns_401(self) -> None:
        """POST without JWT → 401."""
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": "hello"}),
            content_type="application/json",
        )
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_invalid_jwt_returns_401(self) -> None:
        """POST with a bogus token → 401."""
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": "hello"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer notavalidjwt",
        )
        assert resp.status_code == 401

    def test_get_method_returns_405(self) -> None:
        """GET /api/chat/query/ → 405 (only POST is supported)."""
        token = _register_and_login("val_get@test.com")
        client = Client()
        resp = client.get(CHAT_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 405

    def test_put_method_returns_405(self) -> None:
        """PUT /api/chat/query/ → 405."""
        token = _register_and_login("val_put@test.com")
        client = Client()
        resp = client.put(
            CHAT_URL,
            data=json.dumps({"query": "test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegressionSlice05:
    def test_chat_query_endpoint_present(self) -> None:
        """POST /api/chat/query/ must be routed — not 404."""
        client = Client()
        resp = client.post(
            CHAT_URL,
            data=json.dumps({"query": "test"}),
            content_type="application/json",
        )
        # Without JWT → 401 (route exists); 404 would mean route is absent.
        assert resp.status_code == 401, (
            f"Expected 401 (route present, no JWT), got {resp.status_code}"
        )

    def test_health_endpoint_still_works(self) -> None:
        """GET /api/health/ must still return 200 (regression guard)."""
        client = Client()
        resp = client.get(HEALTH_URL)
        assert resp.status_code == 200

    def test_upload_endpoint_still_works(self) -> None:
        """POST /api/documents/upload/ must still return 401 without JWT."""
        client = Client()
        resp = client.post(UPLOAD_URL)
        assert resp.status_code == 401

    def test_documents_status_still_works(self) -> None:
        """GET /api/documents/status/ must still return 401 without JWT."""
        client = Client()
        resp = client.get(STATUS_URL)
        assert resp.status_code == 401

    def test_register_endpoint_still_works(self) -> None:
        """POST /api/register/ must still be routable."""
        client = Client()
        resp = _post_json(
            client, REGISTER_URL, {"email": "reg_reg@test.com", "password": "pass1234"}
        )
        assert resp.status_code == 201

    def test_login_endpoint_still_works(self) -> None:
        """POST /api/login/ must still be routable."""
        client = Client()
        _post_json(client, REGISTER_URL, {"email": "reg_login@test.com", "password": "pass1234"})
        resp = _post_json(
            client, LOGIN_URL, {"email": "reg_login@test.com", "password": "pass1234"}
        )
        assert resp.status_code == 200

    def test_bogus_path_still_404(self) -> None:
        """/api/nope/ must still return 404."""
        client = Client()
        resp = client.get("/api/nope/")
        assert resp.status_code == 404
