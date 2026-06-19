"""Unit tests for the RAG pipeline components (slice 04).

All tests run offline:
  - Embeddings use the deterministic stub (no model download, no network).
  - Chroma uses the temp directory set in config.settings.test.
  - No Celery broker needed (tasks are tested via pipeline functions directly).

Covers:
  - ``extract_text``: PDF (valid with text), TXT, MD.
  - ``run_ingestion``: returns chunk_count > 0 and writes to Chroma.
  - Stub embeddings: deterministic, same text → same vector.
"""

from __future__ import annotations

import os
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Minimal file fixtures (bytes)
# ---------------------------------------------------------------------------

# Valid PDF with extractable "Hello World" text.
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

_TXT_CONTENT = (
    b"This is a plain-text document with enough words to produce at least one chunk "
    b"when split by RecursiveCharacterTextSplitter."
)

_MD_CONTENT = (
    b"# Document Title\n\n"
    b"This markdown document contains enough content to be split into chunks.\n\n"
    b"## Section Two\n\nMore content here for the splitter to work with.\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tmp(content: bytes, suffix: str) -> str:
    """Write *content* to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
    except Exception:
        os.close(fd)
        raise
    return path


# ---------------------------------------------------------------------------
# extract_text tests
# ---------------------------------------------------------------------------


class TestExtractText:
    """``extract_text`` must return non-empty strings for valid files.

    No DB access required — tests operate on raw filesystem paths.
    """

    def test_extract_pdf_returns_text(self) -> None:
        from apps.rag.pipeline import extract_text  # noqa: PLC0415

        path = _write_tmp(_PDF_WITH_TEXT, ".pdf")
        try:
            text = extract_text(path, "application/pdf")
        finally:
            os.unlink(path)
        assert "Hello World" in text

    def test_extract_txt_returns_text(self) -> None:
        from apps.rag.pipeline import extract_text  # noqa: PLC0415

        path = _write_tmp(_TXT_CONTENT, ".txt")
        try:
            text = extract_text(path, "text/plain")
        finally:
            os.unlink(path)
        assert "plain-text document" in text

    def test_extract_md_returns_text(self) -> None:
        from apps.rag.pipeline import extract_text  # noqa: PLC0415

        path = _write_tmp(_MD_CONTENT, ".md")
        try:
            text = extract_text(path, "text/markdown")
        finally:
            os.unlink(path)
        assert "Document Title" in text

    def test_extract_pdf_by_extension_fallback(self) -> None:
        """PDF is detected by extension even when content_type is octet-stream."""
        from apps.rag.pipeline import extract_text  # noqa: PLC0415

        path = _write_tmp(_PDF_WITH_TEXT, ".pdf")
        try:
            text = extract_text(path, "application/octet-stream")
        finally:
            os.unlink(path)
        assert text  # non-empty

    def test_extract_txt_empty_raises_nothing(self) -> None:
        """extract_text itself does not guard against empty — pipeline does."""
        from apps.rag.pipeline import extract_text  # noqa: PLC0415

        path = _write_tmp(b"   ", ".txt")
        try:
            text = extract_text(path, "text/plain")
        finally:
            os.unlink(path)
        # extract_text returns whitespace; run_ingestion will raise ValueError.
        assert text.strip() == ""


# ---------------------------------------------------------------------------
# Stub embeddings tests
# ---------------------------------------------------------------------------


class TestStubEmbeddings:
    """The stub must be deterministic and produce fixed-dim vectors."""

    def test_embed_documents_returns_list_of_vectors(self) -> None:
        from apps.rag.embeddings import _StubEmbeddings  # noqa: PLC0415

        stub = _StubEmbeddings()
        vecs = stub.embed_documents(["hello", "world"])
        assert len(vecs) == 2
        assert all(isinstance(v, list) for v in vecs)
        assert all(len(v) == 32 for v in vecs)

    def test_embed_query_returns_vector(self) -> None:
        from apps.rag.embeddings import _StubEmbeddings  # noqa: PLC0415

        stub = _StubEmbeddings()
        vec = stub.embed_query("test query")
        assert isinstance(vec, list)
        assert len(vec) == 32

    def test_same_text_same_vector(self) -> None:
        """Determinism: same input → same output across calls."""
        from apps.rag.embeddings import _StubEmbeddings  # noqa: PLC0415

        stub = _StubEmbeddings()
        v1 = stub.embed_query("identical text")
        v2 = stub.embed_query("identical text")
        assert v1 == v2

    def test_different_text_different_vector(self) -> None:
        from apps.rag.embeddings import _StubEmbeddings  # noqa: PLC0415

        stub = _StubEmbeddings()
        v1 = stub.embed_query("text A")
        v2 = stub.embed_query("text B")
        assert v1 != v2


# ---------------------------------------------------------------------------
# run_ingestion tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRunIngestion:
    """``run_ingestion`` operates on a real DB + temp Chroma (offline)."""

    def _make_job(self, email: str, content: bytes, suffix: str, ct: str) -> object:
        """Create a user, document, and IngestionJob referencing a temp file."""
        from apps.documents.services import create_document  # noqa: PLC0415
        from apps.rag.models import IngestionJob  # noqa: PLC0415
        from django.contrib.auth import get_user_model  # noqa: PLC0415

        User = get_user_model()
        user = User.objects.create_user(username=email, email=email, password="pass12345")

        from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: PLC0415

        filename = f"doc{suffix}"
        f = SimpleUploadedFile(filename, content, content_type=ct)
        doc = create_document(owner=user, uploaded_file=f)
        job = IngestionJob.objects.create(
            owner=user,
            source_document=doc,
            status=IngestionJob.Status.PENDING,
        )
        return job

    def test_run_ingestion_txt_returns_positive_count(self) -> None:
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_txt@test.com", _TXT_CONTENT, ".txt", "text/plain")
        count = run_ingestion(job)
        assert count > 0

    def test_run_ingestion_md_returns_positive_count(self) -> None:
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_md@test.com", _MD_CONTENT, ".md", "text/markdown")
        count = run_ingestion(job)
        assert count > 0

    def test_run_ingestion_pdf_returns_positive_count(self) -> None:
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_pdf@test.com", _PDF_WITH_TEXT, ".pdf", "application/pdf")
        count = run_ingestion(job)
        assert count > 0

    def test_run_ingestion_writes_to_user_collection(self) -> None:
        """Chroma collection for the job owner has vectors after ingestion."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_chroma@test.com", _TXT_CONTENT, ".txt", "text/plain")
        # Delete any pre-existing vectors for this document (idempotent setup).
        vectorstore.delete_document_vectors(job.owner_id, job.source_document_id)
        col_before = vectorstore.get_collection(job.owner_id).count()
        run_ingestion(job)
        col_after = vectorstore.get_collection(job.owner_id).count()
        assert col_after > col_before

    def test_run_ingestion_upsert_is_idempotent(self) -> None:
        """Re-running ingestion for the same document must not duplicate vectors."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_idem@test.com", _TXT_CONTENT, ".txt", "text/plain")
        run_ingestion(job)
        count_first = vectorstore.get_collection(job.owner_id).count()
        run_ingestion(job)
        count_second = vectorstore.get_collection(job.owner_id).count()
        # Upsert with the same ids should not increase the count.
        assert count_second == count_first

    def test_run_ingestion_empty_raises_value_error(self) -> None:
        """Whitespace-only document must raise ValueError (guards M-006)."""
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_empty@test.com", b"   \n  ", ".txt", "text/plain")
        with pytest.raises(ValueError, match="No extractable text"):
            run_ingestion(job)

    def test_run_ingestion_returns_chunk_count_matches_collection(self) -> None:
        """The returned chunk_count must match vectors actually in Chroma."""
        from apps.rag import vectorstore  # noqa: PLC0415
        from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

        job = self._make_job("ri_match@test.com", _TXT_CONTENT, ".txt", "text/plain")
        returned_count = run_ingestion(job)
        chroma_count = vectorstore.get_collection(job.owner_id).count()
        assert returned_count == chroma_count
