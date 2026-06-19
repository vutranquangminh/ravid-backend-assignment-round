"""Integration tests for the ingestion pipeline and status endpoint (slice 04).

All tests run offline:
  - RAVID_EMBEDDINGS_STUB=True (set in config.settings.test) → no model download.
  - CHROMA_PERSIST_DIR is a temp dir (set in config.settings.test).
  - CELERY_TASK_ALWAYS_EAGER=True → tasks run synchronously in-process.

Covers:
  - Happy path: upload TXT/MD/PDF → poll status → SUCCESS + exact message.
  - IngestionJob has chunk_count > 0 after success.
  - Failure path: empty document → FAILURE on status; failure logged.
  - Status mapping: constructed PENDING/STARTED job → PROCESSING.
  - Isolation: user B cannot read user A's task_id (404).
  - Per-user vector isolation: A's vectors in user_A collection only.
  - Delete removes vectors from Chroma.
  - Missing task_id param → 400.
  - Regression: /api/chat/query/ still 404; /api/documents/status/ present.
"""

from __future__ import annotations

import json
import logging

import pytest
from apps.rag.models import IngestionJob
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

UPLOAD_URL = "/api/documents/upload/"
STATUS_URL = "/api/documents/status/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"

# ---------------------------------------------------------------------------
# Minimal file content
# ---------------------------------------------------------------------------

# Valid PDF with extractable text ("Hello World").
# (Deliberately small; the xref offset is slightly off but pypdf is lenient.)
_PDF_WITH_TEXT = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Hello World) Tj ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n

trailer
<< /Size 6 /Root 1 0 R >>
startxref
441
%%EOF"""

# A minimal but *invalid* PDF that produces no text (pypdf raises on read) —
# used to trigger FAILURE in the pipeline.
_PDF_NO_TEXT = b"%PDF-1.4\n%%EOF"

_TXT_CONTENT = b"This is a plain-text document with enough words to produce at least one chunk."
_MD_CONTENT = b"# Heading\n\nThis markdown file has content that can be split and embedded."

# Empty content → pipeline raises ValueError("No extractable text").
_EMPTY_TXT = b"   \n\t  "


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


def _upload(
    client: Client,
    token: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> object:
    f = SimpleUploadedFile(filename, content, content_type=content_type)
    return client.post(
        UPLOAD_URL,
        data={"file": f},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def _get_status(client: Client, token: str, task_id: str) -> object:
    return client.get(
        STATUS_URL,
        {"task_id": task_id},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ---------------------------------------------------------------------------
# Happy path: upload → status SUCCESS
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIngestionHappyPath:
    def test_upload_txt_then_status_success(self) -> None:
        """TXT upload → eager task runs → status SUCCESS with exact message."""
        token = _register_and_login("ing_txt@test.com")
        client = Client()

        up = _upload(client, token, "doc.txt", _TXT_CONTENT, "text/plain")
        assert up.status_code == 202
        task_id = up.json()["task_id"]

        resp = _get_status(client, token, task_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == task_id
        assert body["status"] == "SUCCESS"
        assert (
            body["message"]
            == "Document successfully parsed, embedded, and indexed in vector storage."
        )

    def test_upload_md_then_status_success(self) -> None:
        """MD upload → eager task runs → status SUCCESS."""
        token = _register_and_login("ing_md@test.com")
        client = Client()

        up = _upload(client, token, "readme.md", _MD_CONTENT, "text/markdown")
        assert up.status_code == 202
        task_id = up.json()["task_id"]

        resp = _get_status(client, token, task_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "SUCCESS"

    def test_upload_pdf_with_text_then_status_success(self) -> None:
        """PDF with extractable text → eager task runs → status SUCCESS."""
        token = _register_and_login("ing_pdf@test.com")
        client = Client()

        up = _upload(client, token, "report.pdf", _PDF_WITH_TEXT, "application/pdf")
        assert up.status_code == 202
        task_id = up.json()["task_id"]

        resp = _get_status(client, token, task_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "SUCCESS"

    def test_ingestion_job_chunk_count_positive(self) -> None:
        """IngestionJob.chunk_count > 0 after a successful pipeline run."""
        token = _register_and_login("ing_chunks@test.com")
        client = Client()

        up = _upload(client, token, "data.txt", _TXT_CONTENT, "text/plain")
        assert up.status_code == 202
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count > 0

    def test_ingestion_writes_to_user_collection(self) -> None:
        """After ingestion the owner's Chroma collection has vectors."""
        from apps.rag import vectorstore  # noqa: PLC0415

        token = _register_and_login("ing_chroma@test.com")
        client = Client()
        user = User.objects.get(email="ing_chroma@test.com")

        up = _upload(client, token, "vec.txt", _TXT_CONTENT, "text/plain")
        assert up.status_code == 202

        collection = vectorstore.get_collection(user.pk)
        assert collection.count() > 0


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIngestionFailure:
    def test_empty_doc_causes_failure_status(self) -> None:
        """Uploading a whitespace-only TXT → status FAILURE + error."""
        token = _register_and_login("ing_fail@test.com")
        client = Client()

        up = _upload(client, token, "empty.txt", _EMPTY_TXT, "text/plain")
        assert up.status_code == 202
        task_id = up.json()["task_id"]

        resp = _get_status(client, token, task_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "FAILURE"
        assert "error" in body
        assert body["error"]  # non-empty error message

    def test_failure_sets_job_row(self) -> None:
        """IngestionJob row carries FAILURE status and error_message."""
        token = _register_and_login("ing_failrow@test.com")
        client = Client()

        up = _upload(client, token, "empty2.txt", _EMPTY_TXT, "text/plain")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.FAILURE
        assert job.error_message  # non-empty

    def test_failure_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Pipeline failures must be captured in structured logs (D-026)."""
        token = _register_and_login("ing_faillog@test.com")
        client = Client()

        with caplog.at_level(logging.ERROR, logger="apps.rag.tasks"):
            _upload(client, token, "empty3.txt", _EMPTY_TXT, "text/plain")

        # At least one ERROR log record from the ingest task.
        assert any(r.levelno >= logging.ERROR for r in caplog.records), (
            "Expected at least one ERROR log record for failed ingestion"
        )

    def test_failure_log_does_not_contain_document_text(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Raw document text must never appear in logs (D-027 / M-008)."""
        secret_text = b"SUPER SECRET DOCUMENT CONTENT XYZ987"
        token = _register_and_login("ing_noleak@test.com")
        client = Client()

        with caplog.at_level(logging.DEBUG):
            _upload(client, token, "secret.txt", secret_text, "text/plain")

        combined = " ".join(r.getMessage() for r in caplog.records)
        assert "SUPER SECRET DOCUMENT CONTENT XYZ987" not in combined, (
            "Document text leaked into logs — M-008 violation"
        )


# ---------------------------------------------------------------------------
# Status mapping: PENDING / STARTED → PROCESSING
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStatusMapping:
    def _make_job(self, status_val: str, email: str) -> tuple:
        user = User.objects.create_user(username=email, email=email, password="pass12345")
        from apps.documents.services import create_document  # noqa: PLC0415

        f = SimpleUploadedFile("x.txt", b"content", content_type="text/plain")
        doc = create_document(owner=user, uploaded_file=f)
        job = IngestionJob.objects.create(
            owner=user,
            source_document=doc,
            status=status_val,
            celery_task_id=f"fake-task-{email}",
        )
        return user, job

    def _token(self, email: str) -> str:
        c = Client()
        _post_json(c, REGISTER_URL, {"email": email, "password": "pass12345"})
        resp = _post_json(c, LOGIN_URL, {"email": email, "password": "pass12345"})
        return resp.json()["token"]

    def test_pending_maps_to_processing(self) -> None:
        user, job = self._make_job("PENDING", "map_pending@test.com")
        token = self._token("map_pending@test.com")
        client = Client()
        resp = _get_status(client, token, job.celery_task_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "PROCESSING"

    def test_started_maps_to_processing(self) -> None:
        user, job = self._make_job("STARTED", "map_started@test.com")
        token = self._token("map_started@test.com")
        client = Client()
        resp = _get_status(client, token, job.celery_task_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "PROCESSING"

    def test_success_maps_to_success(self) -> None:
        user, job = self._make_job("SUCCESS", "map_success@test.com")
        token = self._token("map_success@test.com")
        client = Client()
        resp = _get_status(client, token, job.celery_task_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "SUCCESS"
        assert "message" in body

    def test_failure_maps_to_failure_with_error(self) -> None:
        user = User.objects.create_user(
            username="map_fail@test.com",
            email="map_fail@test.com",
            password="pass12345",
        )
        from apps.documents.services import create_document  # noqa: PLC0415

        f = SimpleUploadedFile("x.txt", b"x", content_type="text/plain")
        doc = create_document(owner=user, uploaded_file=f)
        job = IngestionJob.objects.create(
            owner=user,
            source_document=doc,
            status="FAILURE",
            celery_task_id="fake-task-fail",
            error_message="something went wrong",
        )
        token = self._token("map_fail@test.com")
        client = Client()
        resp = _get_status(client, token, job.celery_task_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "FAILURE"
        assert body["error"] == "something went wrong"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIsolation:
    def test_cross_user_status_returns_404(self) -> None:
        """User B cannot read user A's job status — must return 404 (D-020)."""
        token_a = _register_and_login("iso_a@test.com")
        token_b = _register_and_login("iso_b@test.com")
        client = Client()

        up = _upload(client, token_a, "a.txt", _TXT_CONTENT, "text/plain")
        task_id_a = up.json()["task_id"]

        resp = _get_status(client, token_b, task_id_a)
        assert resp.status_code == 404

    def test_user_a_vectors_not_in_user_b_collection(self) -> None:
        """A's document vectors must be in user_A collection, not in user_B's."""
        from apps.rag import vectorstore  # noqa: PLC0415

        token_a = _register_and_login("iso_vec_a@test.com")
        _register_and_login("iso_vec_b@test.com")  # user B exists but uploads nothing
        client = Client()

        user_a = User.objects.get(email="iso_vec_a@test.com")
        user_b = User.objects.get(email="iso_vec_b@test.com")

        # A uploads a document; B does not.
        up_a = _upload(client, token_a, "a.txt", _TXT_CONTENT, "text/plain")
        doc_id_a = up_a.json()["document_id"]

        col_a = vectorstore.get_collection(user_a.pk)
        col_b = vectorstore.get_collection(user_b.pk)

        # A's document vectors must exist in A's collection.
        a_doc_vecs = col_a.get(where={"document_id": str(doc_id_a)})
        assert len(a_doc_vecs["ids"]) > 0, "User A's vectors should be in A's collection"

        # A's document_id must NOT appear in B's collection.
        b_doc_vecs = (
            col_b.get(where={"document_id": str(doc_id_a)}) if col_b.count() > 0 else {"ids": []}
        )
        assert len(b_doc_vecs["ids"]) == 0, "User A's vectors must not appear in B's collection"

    def test_delete_removes_vectors_from_chroma(self) -> None:
        """Deleting a document also removes its vectors from Chroma."""

        from apps.rag import vectorstore  # noqa: PLC0415

        token = _register_and_login("iso_del@test.com")
        client = Client()
        user = User.objects.get(email="iso_del@test.com")

        up = _upload(client, token, "del.txt", _TXT_CONTENT, "text/plain")
        doc_id = up.json()["document_id"]

        # Verify vectors exist for this specific document before delete.
        col = vectorstore.get_collection(user.pk)
        doc_vectors_before = col.get(where={"document_id": str(doc_id)})
        assert len(doc_vectors_before["ids"]) > 0, "Expected vectors for the document before delete"
        count_before = col.count()

        client.delete(
            f"/api/documents/{doc_id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        # After delete, this document's vectors must be gone and the total count dropped.
        col = vectorstore.get_collection(user.pk)
        doc_vectors_after = col.get(where={"document_id": str(doc_id)})
        assert len(doc_vectors_after["ids"]) == 0, "Expected document vectors to be removed"
        assert col.count() < count_before, "Collection count should decrease after vector delete"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStatusValidation:
    def test_missing_task_id_returns_400(self) -> None:
        """GET /api/documents/status/ without task_id → 400."""
        token = _register_and_login("val_missing@test.com")
        client = Client()
        resp = client.get(STATUS_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_unknown_task_id_returns_404(self) -> None:
        """GET /api/documents/status/?task_id=<nonexistent> → 404."""
        token = _register_and_login("val_unknown@test.com")
        client = Client()
        resp = _get_status(client, token, "nonexistent-uuid-xyz")
        assert resp.status_code == 404

    def test_no_jwt_returns_401(self) -> None:
        """GET /api/documents/status/ without JWT → 401."""
        client = Client()
        resp = client.get(STATUS_URL, {"task_id": "anything"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegressionSlice04:
    def test_chat_query_still_absent(self) -> None:
        """POST /api/chat/query/ must still return 404 (slice 05 not landed)."""
        client = Client()
        resp = client.post(
            "/api/chat/query/",
            data=json.dumps({"query": "hello"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_status_endpoint_present(self) -> None:
        """GET /api/documents/status/ must NOT return 404 (slice 04 landed)."""
        client = Client()
        resp = client.get(STATUS_URL)
        # Without JWT → 401, not 404.
        assert resp.status_code == 401
