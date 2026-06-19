"""Integration tests for the document management API (slice 03).

Covers:
  POST   /api/documents/upload/   — happy path (PDF/TXT/MD), rejections, auth
  GET    /api/documents/          — per-user isolation
  DELETE /api/documents/<pk>/     — owner can delete; cross-user → 404; file gone
  Regression: /api/documents/status/ still absent; /api/documents/upload/ present
"""

from __future__ import annotations

import json
import os

import pytest
from apps.documents.models import Document
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

User = get_user_model()

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

UPLOAD_URL = "/api/documents/upload/"
LIST_URL = "/api/documents/"
LOGIN_URL = "/api/login/"
REGISTER_URL = "/api/register/"


# ---------------------------------------------------------------------------
# Minimal valid file content
# ---------------------------------------------------------------------------

# A minimal but structurally valid PDF (no real content, but parseable header+footer)
_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
_TXT_BYTES = b"Hello, this is plain text content.\n"
_MD_BYTES = b"# Title\n\nThis is **markdown** content.\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _get_token(email: str, password: str) -> str:
    """Register a user and return their JWT access token."""
    client = Client()
    _post_json(client, REGISTER_URL, {"email": email, "password": password})
    response = _post_json(client, LOGIN_URL, {"email": email, "password": password})
    assert response.status_code == 200, f"Login failed: {response.json()}"
    return response.json()["token"]


def _upload(client: Client, token: str, filename: str, content: bytes, content_type: str):
    """POST a file to the upload endpoint with the given JWT."""
    f = SimpleUploadedFile(filename, content, content_type=content_type)
    return client.post(
        UPLOAD_URL,
        data={"file": f},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ---------------------------------------------------------------------------
# Happy path: upload PDF / TXT / MD
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUploadHappyPath:
    def test_upload_pdf_returns_202(self) -> None:
        token = _get_token("pdf_user@example.com", "strongpass1")
        client = Client()
        response = _upload(client, token, "report.pdf", _PDF_BYTES, "application/pdf")
        assert response.status_code == 202
        body = response.json()
        assert body["message"] == "Document uploaded and ingestion started"
        assert "document_id" in body
        assert "task_id" in body
        assert isinstance(body["document_id"], int)
        assert body["task_id"]  # non-empty

    def test_upload_txt_returns_202(self) -> None:
        token = _get_token("txt_user@example.com", "strongpass1")
        client = Client()
        response = _upload(client, token, "notes.txt", _TXT_BYTES, "text/plain")
        assert response.status_code == 202
        body = response.json()
        assert "document_id" in body
        assert "task_id" in body

    def test_upload_md_returns_202(self) -> None:
        token = _get_token("md_user@example.com", "strongpass1")
        client = Client()
        response = _upload(client, token, "readme.md", _MD_BYTES, "text/markdown")
        assert response.status_code == 202
        body = response.json()
        assert "document_id" in body
        assert "task_id" in body

    def test_upload_creates_document_row(self) -> None:
        token = _get_token("row_user@example.com", "strongpass1")
        client = Client()
        before_count = Document.objects.count()
        response = _upload(client, token, "doc.pdf", _PDF_BYTES, "application/pdf")
        assert response.status_code == 202
        assert Document.objects.count() == before_count + 1

    def test_upload_document_owned_by_caller(self) -> None:
        email = "owner_user@example.com"
        token = _get_token(email, "strongpass1")
        client = Client()
        response = _upload(client, token, "mine.pdf", _PDF_BYTES, "application/pdf")
        assert response.status_code == 202
        doc_id = response.json()["document_id"]
        doc = Document.objects.get(pk=doc_id)
        user = User.objects.get(username=email)
        assert doc.owner == user

    def test_upload_pdf_octet_stream_tolerated(self) -> None:
        """application/octet-stream is tolerated when extension is valid."""
        token = _get_token("octet_user@example.com", "strongpass1")
        client = Client()
        response = _upload(client, token, "file.pdf", _PDF_BYTES, "application/octet-stream")
        assert response.status_code == 202

    def test_ingestion_task_runs_and_advances_status(self) -> None:
        """In eager mode the task runs inline; status should advance past UPLOADED."""
        token = _get_token("task_user@example.com", "strongpass1")
        client = Client()
        # Use a TXT file so the pipeline can extract text and succeed.
        response = _upload(client, token, "eager.txt", _TXT_BYTES, "text/plain")
        assert response.status_code == 202
        doc = Document.objects.get(pk=response.json()["document_id"])
        # In eager mode the full pipeline runs synchronously: SUCCESS or FAILURE,
        # but never still UPLOADED (the task always advances the status).
        assert doc.status != "UPLOADED", f"Expected status to advance, got {doc.status!r}"


# ---------------------------------------------------------------------------
# Upload validation rejections
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUploadValidation:
    def test_exe_file_rejected_400_exact_message(self) -> None:
        token = _get_token("exe_user@example.com", "strongpass1")
        client = Client()
        f = SimpleUploadedFile(
            "malware.exe", b"MZ\x00\x00", content_type="application/x-msdownload"
        )
        response = client.post(
            UPLOAD_URL,
            data={"file": f},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response.status_code == 400
        body = response.json()
        assert body == {
            "error": "Invalid file format. Only PDF, TXT, and Markdown files are allowed."
        }

    def test_unknown_extension_rejected_400_exact_message(self) -> None:
        token = _get_token("ext_user@example.com", "strongpass1")
        client = Client()
        f = SimpleUploadedFile("data.csv", b"col1,col2\n1,2\n", content_type="text/csv")
        response = client.post(
            UPLOAD_URL,
            data={"file": f},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response.status_code == 400
        body = response.json()
        assert body == {
            "error": "Invalid file format. Only PDF, TXT, and Markdown files are allowed."
        }

    def test_oversize_file_rejected_400(self) -> None:
        token = _get_token("big_user@example.com", "strongpass1")
        client = Client()
        # Build a file just over 10 MB.
        big_content = b"x" * (10 * 1024 * 1024 + 1)
        f = SimpleUploadedFile("huge.txt", big_content, content_type="text/plain")
        response = client.post(
            UPLOAD_URL,
            data={"file": f},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert "10" in body["error"] or "large" in body["error"].lower()

    def test_no_jwt_returns_401(self) -> None:
        client = Client()
        f = SimpleUploadedFile("doc.pdf", _PDF_BYTES, content_type="application/pdf")
        response = client.post(UPLOAD_URL, data={"file": f})
        assert response.status_code == 401
        body = response.json()
        assert "error" in body

    def test_no_file_field_returns_400(self) -> None:
        token = _get_token("nofile_user@example.com", "strongpass1")
        client = Client()
        response = client.post(
            UPLOAD_URL,
            data={},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response.status_code == 400
        assert "error" in response.json()


# ---------------------------------------------------------------------------
# List endpoint: per-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDocumentList:
    def test_list_returns_own_documents_only(self) -> None:
        token_a = _get_token("list_a@example.com", "strongpass1")
        token_b = _get_token("list_b@example.com", "strongpass1")
        client = Client()

        # A uploads a file.
        _upload(client, token_a, "a.pdf", _PDF_BYTES, "application/pdf")

        # B's list should be empty (0 docs for B).
        resp_b = client.get(LIST_URL, HTTP_AUTHORIZATION=f"Bearer {token_b}")
        assert resp_b.status_code == 200
        assert resp_b.json() == []

        # A's list should have exactly 1 doc.
        resp_a = client.get(LIST_URL, HTTP_AUTHORIZATION=f"Bearer {token_a}")
        assert resp_a.status_code == 200
        data = resp_a.json()
        assert len(data) == 1
        assert data[0]["original_name"] == "a.pdf"

    def test_list_no_jwt_returns_401(self) -> None:
        client = Client()
        response = client.get(LIST_URL)
        assert response.status_code == 401

    def test_list_response_shape(self) -> None:
        token = _get_token("shape_user@example.com", "strongpass1")
        client = Client()
        _upload(client, token, "shape.pdf", _PDF_BYTES, "application/pdf")
        resp = client.get(LIST_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 200
        doc = resp.json()[0]
        for field in ("id", "original_name", "content_type", "size_bytes", "status", "uploaded_at"):
            assert field in doc, f"Field '{field}' missing from list response"


# ---------------------------------------------------------------------------
# Delete endpoint: isolation + file cleanup
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDocumentDelete:
    def test_owner_can_delete_own_document(self) -> None:
        token = _get_token("del_owner@example.com", "strongpass1")
        client = Client()
        up = _upload(client, token, "todel.pdf", _PDF_BYTES, "application/pdf")
        doc_id = up.json()["document_id"]

        resp = client.delete(
            f"/api/documents/{doc_id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 204
        assert not Document.objects.filter(pk=doc_id).exists()

    def test_delete_removes_file_from_disk(self) -> None:
        token = _get_token("del_disk@example.com", "strongpass1")
        client = Client()
        up = _upload(client, token, "ondisk.pdf", _PDF_BYTES, "application/pdf")
        doc_id = up.json()["document_id"]
        doc = Document.objects.get(pk=doc_id)
        file_path = doc.file.path

        assert os.path.exists(file_path), "File should exist before delete"

        client.delete(
            f"/api/documents/{doc_id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert not os.path.exists(file_path), "File should be gone after delete"

    def test_cross_user_delete_returns_404(self) -> None:
        token_a = _get_token("del_cross_a@example.com", "strongpass1")
        token_b = _get_token("del_cross_b@example.com", "strongpass1")
        client = Client()

        up = _upload(client, token_a, "private.pdf", _PDF_BYTES, "application/pdf")
        doc_id = up.json()["document_id"]

        resp = client.delete(
            f"/api/documents/{doc_id}/",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )
        assert resp.status_code == 404
        # Resource still exists for A.
        assert Document.objects.filter(pk=doc_id).exists()

    def test_missing_pk_returns_404(self) -> None:
        token = _get_token("del_missing@example.com", "strongpass1")
        client = Client()
        resp = client.delete(
            "/api/documents/99999/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 404

    def test_delete_no_jwt_returns_401(self) -> None:
        client = Client()
        resp = client.delete("/api/documents/1/")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Regression: absent endpoints still absent, upload now present
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEndpointPresence:
    def test_upload_endpoint_is_present(self) -> None:
        """POST /api/documents/upload/ must NOT return 404 anymore (slice 03 landed)."""
        client = Client()
        # Without a token we expect 401, not 404.
        f = SimpleUploadedFile("x.pdf", _PDF_BYTES, content_type="application/pdf")
        resp = client.post(UPLOAD_URL, data={"file": f})
        assert resp.status_code != 404, "Upload endpoint should be routed"
        assert resp.status_code == 401

    def test_status_endpoint_now_present(self) -> None:
        """GET /api/documents/status/ must NOT return 404 (slice 04 landed)."""
        client = Client()
        resp = client.get("/api/documents/status/")
        # Without a JWT we expect 401, not 404.
        assert resp.status_code != 404, "Status endpoint should be routed (slice 04)"
        assert resp.status_code == 401

    def test_chat_query_still_absent(self) -> None:
        client = Client()
        resp = client.post(
            "/api/chat/query/",
            data=json.dumps({"query": "hello"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
