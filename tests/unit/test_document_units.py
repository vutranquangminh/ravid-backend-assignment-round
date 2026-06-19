"""Unit tests for documents app: serializer validation matrix + services.

These tests run offline (no broker, Celery in eager mode via test settings)
and do not touch ML libraries.
"""

from __future__ import annotations

import os

import pytest
from apps.documents.models import Document
from apps.documents.serializers import DocumentUploadSerializer
from apps.documents.services import create_document, delete_document
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

User = get_user_model()

# ---------------------------------------------------------------------------
# Shared file fixtures
# ---------------------------------------------------------------------------

_PDF_BYTES = b"%PDF-1.4\n%%EOF"
_TXT_BYTES = b"plain text"
_MD_BYTES = b"# Heading\ncontent"
_EXE_BYTES = b"MZ\x00\x00"


def _make_file(name: str, content: bytes, ct: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=ct)


# ---------------------------------------------------------------------------
# Serializer validation matrix
# ---------------------------------------------------------------------------


class TestDocumentUploadSerializerValidation:
    """No DB access needed — serializer validates in memory."""

    def _validate(self, name: str, content: bytes, ct: str) -> object:
        f = _make_file(name, content, ct)
        s = DocumentUploadSerializer(data={"file": f})
        s.is_valid(raise_exception=True)
        return s.validated_data["file"]

    def test_pdf_with_application_pdf_passes(self) -> None:
        result = self._validate("doc.pdf", _PDF_BYTES, "application/pdf")
        assert result is not None

    def test_txt_with_text_plain_passes(self) -> None:
        result = self._validate("notes.txt", _TXT_BYTES, "text/plain")
        assert result is not None

    def test_md_with_text_markdown_passes(self) -> None:
        result = self._validate("readme.md", _MD_BYTES, "text/markdown")
        assert result is not None

    def test_md_with_text_x_markdown_passes(self) -> None:
        result = self._validate("readme.md", _MD_BYTES, "text/x-markdown")
        assert result is not None

    def test_pdf_with_octet_stream_passes(self) -> None:
        """octet-stream is tolerated when extension is valid."""
        result = self._validate("file.pdf", _PDF_BYTES, "application/octet-stream")
        assert result is not None

    def test_exe_extension_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            self._validate("malware.exe", _EXE_BYTES, "application/x-msdownload")
        detail = exc_info.value.detail
        # Flatten the error detail to a string for assertion.
        msg = _flatten_detail(detail)
        assert "Invalid file format. Only PDF, TXT, and Markdown files are allowed." in msg

    def test_csv_extension_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            self._validate("data.csv", b"col1,col2\n", "text/csv")
        msg = _flatten_detail(exc_info.value.detail)
        assert "Invalid file format. Only PDF, TXT, and Markdown files are allowed." in msg

    def test_bad_content_type_pdf_extension_rejected(self) -> None:
        """If MIME type is not in the allowlist, reject regardless of extension."""
        with pytest.raises(ValidationError):
            self._validate("doc.pdf", _PDF_BYTES, "application/x-pdf")

    def test_oversize_rejected(self) -> None:
        big = b"x" * (10 * 1024 * 1024 + 1)
        with pytest.raises(ValidationError) as exc_info:
            self._validate("big.txt", big, "text/plain")
        msg = _flatten_detail(exc_info.value.detail)
        assert "10" in msg or "large" in msg.lower()

    def test_exactly_max_size_passes(self) -> None:
        at_limit = b"x" * (10 * 1024 * 1024)
        result = self._validate("max.txt", at_limit, "text/plain")
        assert result is not None

    def test_content_type_parameters_stripped(self) -> None:
        """MIME params like '; charset=utf-8' must not cause rejection."""
        result = self._validate("doc.txt", _TXT_BYTES, "text/plain; charset=utf-8")
        assert result is not None

    def test_missing_file_field_raises_validation_error(self) -> None:
        s = DocumentUploadSerializer(data={})
        assert not s.is_valid()
        assert "file" in s.errors


# ---------------------------------------------------------------------------
# Service: create_document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreateDocument:
    def test_creates_document_row(self) -> None:
        user = User.objects.create_user(
            username="svc_create@test.com",
            email="svc_create@test.com",
            password="pass12345",
        )
        f = _make_file("report.pdf", _PDF_BYTES, "application/pdf")
        doc = create_document(owner=user, uploaded_file=f)
        assert doc.pk is not None
        assert doc.owner == user
        assert doc.original_name == "report.pdf"
        assert doc.content_type == "application/pdf"
        assert doc.size_bytes == len(_PDF_BYTES)
        assert doc.status == "UPLOADED"

    def test_file_saved_to_storage(self) -> None:
        user = User.objects.create_user(
            username="svc_file@test.com",
            email="svc_file@test.com",
            password="pass12345",
        )
        f = _make_file("save.txt", _TXT_BYTES, "text/plain")
        doc = create_document(owner=user, uploaded_file=f)
        assert doc.file.name  # non-empty path
        assert doc.file.name.startswith(f"uploads/user_{user.pk}/")
        assert os.path.exists(doc.file.path)


# ---------------------------------------------------------------------------
# Service: delete_document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeleteDocument:
    def _setup_user_and_doc(self, email: str) -> tuple:
        user = User.objects.create_user(username=email, email=email, password="pass12345")
        f = _make_file("to_delete.pdf", _PDF_BYTES, "application/pdf")
        doc = create_document(owner=user, uploaded_file=f)
        return user, doc

    def test_delete_removes_db_row(self) -> None:
        user, doc = self._setup_user_and_doc("del_row@test.com")
        pk = doc.pk
        delete_document(owner=user, pk=pk)
        assert not Document.objects.filter(pk=pk).exists()

    def test_delete_removes_file_from_disk(self) -> None:
        user, doc = self._setup_user_and_doc("del_disk2@test.com")
        file_path = doc.file.path
        assert os.path.exists(file_path)
        delete_document(owner=user, pk=doc.pk)
        assert not os.path.exists(file_path)

    def test_cross_user_delete_raises_does_not_exist(self) -> None:
        user_a, doc = self._setup_user_and_doc("del_cross_a2@test.com")
        user_b = User.objects.create_user(
            username="del_cross_b2@test.com",
            email="del_cross_b2@test.com",
            password="pass12345",
        )
        with pytest.raises(Document.DoesNotExist):
            delete_document(owner=user_b, pk=doc.pk)
        # Doc still exists.
        assert Document.objects.filter(pk=doc.pk).exists()

    def test_missing_pk_raises_does_not_exist(self) -> None:
        user = User.objects.create_user(
            username="del_miss@test.com",
            email="del_miss@test.com",
            password="pass12345",
        )
        with pytest.raises(Document.DoesNotExist):
            delete_document(owner=user, pk=99999)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_detail(detail: object) -> str:
    """Recursively flatten a DRF ValidationError detail to a single string."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return " ".join(_flatten_detail(d) for d in detail)
    if isinstance(detail, dict):
        return " ".join(_flatten_detail(v) for v in detail.values())
    return str(detail)
