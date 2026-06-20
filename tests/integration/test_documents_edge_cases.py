"""Edge-case integration tests for the documents app (slice 03).

Targets ``apps/documents`` upload / list / delete views, the upload
serializer's validation, and the storage service.  Complements
``test_ingestion_api.py`` (which focuses on the async pipeline) by
exhaustively exercising the *synchronous* upload contract and the
per-user isolation guarantees.

All tests run fully offline / deterministically (config.settings.test):
  - RAVID_EMBEDDINGS_STUB=True   → no model download.
  - MEDIA_ROOT is a temp dir     → uploads never touch the repo.
  - CHROMA_PERSIST_DIR is a temp dir.
  - CELERY_TASK_ALWAYS_EAGER=True → ingestion runs in-process.

Covered (per the assessment decisions register):
  - Upload each allowed type (.pdf/.txt/.md) → 202 {message,document_id,task_id};
    file persisted under uploads/user_<id>/.
  - Reject .exe/.docx/.csv/.json by extension → 400 with the EXACT message.
  - Extension valid but content-type clearly wrong (.pdf + image/png) → 400.
  - Empty file → 400 (DRF FileField rejects before the size check).
  - Filenames with spaces / unicode / path-traversal-ish stored safely.
  - Size: just over 10 MB → 400; at / under the limit → 202.
  - Auth: upload / list / delete without a token → 401 (D-021).
  - List: only the caller's docs, correct fields, empty for a new user.
  - Delete: own doc → 204 + file removed; missing id → 404; another
    user's id → 404 (NOT 403, D-020); deleting twice → 404 the 2nd time.
"""

from __future__ import annotations

import json
import os

import pytest
from apps.documents.models import Document
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

UPLOAD_URL = "/api/documents/upload/"
LIST_URL = "/api/documents/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"

# Exact strings the contract pins (D-018 / D-022).
BAD_FORMAT_MESSAGE = "Invalid file format. Only PDF, TXT, and Markdown files are allowed."
TOO_LARGE_MESSAGE = "File too large. Maximum allowed size is 10 MB."

# Field set the list serializer must expose (D-017 list shape).
LIST_FIELDS = {"id", "original_name", "content_type", "size_bytes", "status", "uploaded_at"}

# Cheap valid PDF header — enough bytes for the parser to accept the file as a
# .pdf; the ingestion pipeline result is not asserted in these tests.
PDF_BYTES = b"%PDF-1.4\nHello World PDF body with enough text to chunk and embed.\n%%EOF"
TXT_BYTES = b"A plain-text document with plenty of words so the pipeline can chunk it."
MD_BYTES = b"# Title\n\nMarkdown body with enough content to be split and embedded.\n"

# 10 MB limit in bytes (MAX_UPLOAD_MB defaults to 10).
MAX_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers (kept local to this file)
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


def _auth(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _upload(
    client: Client,
    token: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> object:
    f = SimpleUploadedFile(filename, content, content_type=content_type)
    return client.post(UPLOAD_URL, data={"file": f}, **_auth(token))


# ---------------------------------------------------------------------------
# Upload happy path — each allowed type
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUploadAllowedTypes:
    def test_upload_txt_returns_202_envelope(self) -> None:
        token = _register_and_login("edge_txt@test.com")
        client = Client()
        resp = _upload(client, token, "notes.txt", TXT_BYTES, "text/plain")
        assert resp.status_code == 202
        body = resp.json()
        assert set(body) == {"message", "document_id", "task_id"}
        assert body["message"] == "Document uploaded and ingestion started"
        assert isinstance(body["document_id"], int)
        assert isinstance(body["task_id"], str) and body["task_id"]

    def test_upload_md_returns_202(self) -> None:
        token = _register_and_login("edge_md@test.com")
        client = Client()
        resp = _upload(client, token, "README.md", MD_BYTES, "text/markdown")
        assert resp.status_code == 202
        assert "document_id" in resp.json()

    def test_upload_md_x_markdown_content_type_accepted(self) -> None:
        """``text/x-markdown`` is an accepted alias for Markdown."""
        token = _register_and_login("edge_xmd@test.com")
        client = Client()
        resp = _upload(client, token, "doc.md", MD_BYTES, "text/x-markdown")
        assert resp.status_code == 202

    def test_upload_pdf_returns_202(self) -> None:
        token = _register_and_login("edge_pdf@test.com")
        client = Client()
        resp = _upload(client, token, "report.pdf", PDF_BYTES, "application/pdf")
        assert resp.status_code == 202
        assert "document_id" in resp.json()

    def test_upload_octet_stream_with_valid_extension_accepted(self) -> None:
        """A generic ``application/octet-stream`` type is tolerated when the
        extension is valid (curl/browser fall-back)."""
        token = _register_and_login("edge_octet@test.com")
        client = Client()
        resp = _upload(client, token, "data.txt", TXT_BYTES, "application/octet-stream")
        assert resp.status_code == 202

    def test_uppercase_extension_accepted(self) -> None:
        """Extension matching is case-insensitive (.TXT == .txt)."""
        token = _register_and_login("edge_upper@test.com")
        client = Client()
        resp = _upload(client, token, "LOUD.TXT", TXT_BYTES, "text/plain")
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# File persistence on disk
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUploadPersistence:
    def test_file_persisted_under_user_subdir(self) -> None:
        """The stored file lands under ``uploads/user_<id>/`` and exists on disk."""
        token = _register_and_login("edge_persist@test.com")
        client = Client()
        resp = _upload(client, token, "keep.txt", TXT_BYTES, "text/plain")
        doc_id = resp.json()["document_id"]

        user = User.objects.get(email="edge_persist@test.com")
        doc = Document.objects.get(pk=doc_id)
        assert doc.file.name.startswith(f"uploads/user_{user.pk}/")
        assert os.path.exists(doc.file.path)
        assert os.path.getsize(doc.file.path) == len(TXT_BYTES)

    def test_metadata_recorded_on_row(self) -> None:
        """original_name, content_type and size_bytes mirror the upload."""
        token = _register_and_login("edge_meta@test.com")
        client = Client()
        resp = _upload(client, token, "meta.md", MD_BYTES, "text/markdown")
        doc = Document.objects.get(pk=resp.json()["document_id"])
        assert doc.original_name == "meta.md"
        assert doc.content_type == "text/markdown"
        assert doc.size_bytes == len(MD_BYTES)

    def test_two_uploads_same_name_do_not_collide(self) -> None:
        """uuid-prefixed paths keep same-named uploads on separate files."""
        token = _register_and_login("edge_collide@test.com")
        client = Client()
        r1 = _upload(client, token, "dup.txt", TXT_BYTES, "text/plain")
        r2 = _upload(client, token, "dup.txt", TXT_BYTES, "text/plain")
        d1 = Document.objects.get(pk=r1.json()["document_id"])
        d2 = Document.objects.get(pk=r2.json()["document_id"])
        assert d1.file.name != d2.file.name
        assert os.path.exists(d1.file.path)
        assert os.path.exists(d2.file.path)


# ---------------------------------------------------------------------------
# Reject by extension
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRejectByExtension:
    @pytest.mark.parametrize(
        ("filename", "content_type"),
        [
            ("malware.exe", "application/octet-stream"),
            (
                "doc.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            ("table.csv", "text/csv"),
            ("payload.json", "application/json"),
            ("image.png", "image/png"),
            ("archive.zip", "application/zip"),
        ],
    )
    def test_disallowed_extension_returns_400_exact_message(
        self, filename: str, content_type: str
    ) -> None:
        token = _register_and_login(f"edge_ext_{filename.replace('.', '_')}@test.com")
        client = Client()
        resp = _upload(client, token, filename, b"some bytes here", content_type)
        assert resp.status_code == 400
        assert resp.json() == {"error": BAD_FORMAT_MESSAGE}

    def test_no_extension_returns_400(self) -> None:
        token = _register_and_login("edge_noext@test.com")
        client = Client()
        resp = _upload(client, token, "READMEnoext", TXT_BYTES, "text/plain")
        assert resp.status_code == 400
        assert resp.json() == {"error": BAD_FORMAT_MESSAGE}

    def test_double_extension_uses_final_segment(self) -> None:
        """``evil.txt.exe`` is rejected — the real extension is ``.exe``."""
        token = _register_and_login("edge_double@test.com")
        client = Client()
        resp = _upload(client, token, "evil.txt.exe", b"x", "application/octet-stream")
        assert resp.status_code == 400
        assert resp.json() == {"error": BAD_FORMAT_MESSAGE}


# ---------------------------------------------------------------------------
# Reject by content-type mismatch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRejectByContentType:
    def test_pdf_extension_with_image_content_type_rejected(self) -> None:
        """Valid extension but a clearly-wrong content-type → 400."""
        token = _register_and_login("edge_ct_png@test.com")
        client = Client()
        resp = _upload(client, token, "fake.pdf", PDF_BYTES, "image/png")
        assert resp.status_code == 400
        assert resp.json() == {"error": BAD_FORMAT_MESSAGE}

    def test_txt_extension_with_executable_content_type_rejected(self) -> None:
        token = _register_and_login("edge_ct_exe@test.com")
        client = Client()
        resp = _upload(client, token, "real.txt", TXT_BYTES, "application/x-msdownload")
        assert resp.status_code == 400
        assert resp.json() == {"error": BAD_FORMAT_MESSAGE}

    def test_content_type_with_charset_param_is_normalised(self) -> None:
        """``text/plain; charset=utf-8`` strips the param and is accepted."""
        token = _register_and_login("edge_ct_charset@test.com")
        client = Client()
        resp = _upload(client, token, "charset.txt", TXT_BYTES, "text/plain; charset=utf-8")
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Empty file
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmptyFile:
    def test_empty_txt_returns_400(self) -> None:
        """A zero-byte upload is rejected (DRF FileField guards empty files)."""
        token = _register_and_login("edge_empty@test.com")
        client = Client()
        resp = _upload(client, token, "empty.txt", b"", "text/plain")
        assert resp.status_code == 400
        body = resp.json()
        assert set(body) == {"error"}
        assert isinstance(body["error"], str) and body["error"]

    def test_empty_file_creates_no_document_row(self) -> None:
        token = _register_and_login("edge_empty_norow@test.com")
        client = Client()
        _upload(client, token, "empty2.txt", b"", "text/plain")
        user = User.objects.get(email="edge_empty_norow@test.com")
        assert Document.objects.filter(owner=user).count() == 0


# ---------------------------------------------------------------------------
# Filenames: spaces, unicode, path traversal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFilenameSafety:
    def test_path_traversal_filename_stored_under_media(self) -> None:
        """``../escape.txt`` must not climb out of MEDIA_ROOT/uploads."""
        token = _register_and_login("edge_traversal@test.com")
        client = Client()
        resp = _upload(client, token, "../escape.txt", TXT_BYTES, "text/plain")
        assert resp.status_code == 202

        user = User.objects.get(email="edge_traversal@test.com")
        doc = Document.objects.get(pk=resp.json()["document_id"])
        # basename is taken from the upload; the leading ../ is dropped.
        assert doc.original_name == "escape.txt"
        assert doc.file.name.startswith(f"uploads/user_{user.pk}/")
        assert ".." not in doc.file.name
        resolved = os.path.abspath(doc.file.path)
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        assert resolved.startswith(media_root)
        assert os.path.exists(doc.file.path)

    def test_filename_with_spaces_stored(self) -> None:
        token = _register_and_login("edge_spaces@test.com")
        client = Client()
        resp = _upload(client, token, "my report final.txt", TXT_BYTES, "text/plain")
        assert resp.status_code == 202
        doc = Document.objects.get(pk=resp.json()["document_id"])
        assert os.path.exists(doc.file.path)

    def test_unicode_filename_stored(self) -> None:
        token = _register_and_login("edge_unicode@test.com")
        client = Client()
        resp = _upload(client, token, "résumé_文档.md", MD_BYTES, "text/markdown")
        assert resp.status_code == 202
        doc = Document.objects.get(pk=resp.json()["document_id"])
        assert os.path.exists(doc.file.path)
        assert doc.original_name == "résumé_文档.md"


# ---------------------------------------------------------------------------
# Size limit boundaries (10 MB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSizeLimits:
    def test_just_over_limit_returns_400(self) -> None:
        token = _register_and_login("edge_over@test.com")
        client = Client()
        content = b"%PDF-1.4\n" + b"0" * (MAX_BYTES + 1)
        resp = _upload(client, token, "huge.pdf", content, "application/pdf")
        assert resp.status_code == 400
        assert resp.json() == {"error": TOO_LARGE_MESSAGE}

    def test_exactly_at_limit_accepted(self) -> None:
        """A file whose total size is exactly 10 MB is allowed (boundary)."""
        token = _register_and_login("edge_atlimit@test.com")
        client = Client()
        header = b"%PDF-1.4\n"
        content = header + b"0" * (MAX_BYTES - len(header))
        assert len(content) == MAX_BYTES
        resp = _upload(client, token, "atlimit.pdf", content, "application/pdf")
        assert resp.status_code == 202

    def test_just_under_limit_accepted(self) -> None:
        token = _register_and_login("edge_under@test.com")
        client = Client()
        content = b"%PDF-1.4\n" + b"0" * (MAX_BYTES - 100)
        resp = _upload(client, token, "under.pdf", content, "application/pdf")
        assert resp.status_code == 202

    def test_oversize_creates_no_document_row(self) -> None:
        token = _register_and_login("edge_over_norow@test.com")
        client = Client()
        content = b"%PDF-1.4\n" + b"0" * (MAX_BYTES + 1)
        _upload(client, token, "huge2.pdf", content, "application/pdf")
        user = User.objects.get(email="edge_over_norow@test.com")
        assert Document.objects.filter(owner=user).count() == 0


# ---------------------------------------------------------------------------
# Missing file field
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMissingFile:
    def test_no_file_field_returns_400(self) -> None:
        token = _register_and_login("edge_nofile@test.com")
        client = Client()
        resp = client.post(UPLOAD_URL, data={}, **_auth(token))
        assert resp.status_code == 400
        assert set(resp.json()) == {"error"}


# ---------------------------------------------------------------------------
# Authentication required (D-021)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuthRequired:
    def test_upload_without_token_returns_401(self) -> None:
        client = Client()
        f = SimpleUploadedFile("x.txt", TXT_BYTES, content_type="text/plain")
        resp = client.post(UPLOAD_URL, data={"file": f})
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_list_without_token_returns_401(self) -> None:
        client = Client()
        resp = client.get(LIST_URL)
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_delete_without_token_returns_401(self) -> None:
        client = Client()
        resp = client.delete("/api/documents/1/")
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_upload_with_garbage_token_returns_401(self) -> None:
        client = Client()
        f = SimpleUploadedFile("x.txt", TXT_BYTES, content_type="text/plain")
        resp = client.post(
            UPLOAD_URL,
            data={"file": f},
            HTTP_AUTHORIZATION="Bearer not.a.real.jwt",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestListView:
    def test_new_user_list_is_empty(self) -> None:
        token = _register_and_login("edge_list_empty@test.com")
        client = Client()
        resp = client.get(LIST_URL, **_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_expected_fields(self) -> None:
        token = _register_and_login("edge_list_fields@test.com")
        client = Client()
        _upload(client, token, "f.txt", TXT_BYTES, "text/plain")
        resp = client.get(LIST_URL, **_auth(token))
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        item = items[0]
        assert set(item) == LIST_FIELDS
        assert item["original_name"] == "f.txt"
        assert item["content_type"] == "text/plain"
        assert item["size_bytes"] == len(TXT_BYTES)
        assert isinstance(item["id"], int)
        assert isinstance(item["status"], str)
        assert isinstance(item["uploaded_at"], str)

    def test_list_returns_all_owner_docs(self) -> None:
        token = _register_and_login("edge_list_many@test.com")
        client = Client()
        _upload(client, token, "a.txt", TXT_BYTES, "text/plain")
        _upload(client, token, "b.md", MD_BYTES, "text/markdown")
        _upload(client, token, "c.pdf", PDF_BYTES, "application/pdf")
        resp = client.get(LIST_URL, **_auth(token))
        assert resp.status_code == 200
        names = {d["original_name"] for d in resp.json()}
        assert names == {"a.txt", "b.md", "c.pdf"}

    def test_list_shows_only_callers_docs(self) -> None:
        """User A's list must never contain user B's documents (isolation)."""
        token_a = _register_and_login("edge_list_iso_a@test.com")
        token_b = _register_and_login("edge_list_iso_b@test.com")
        client = Client()

        _upload(client, token_a, "a_only.txt", TXT_BYTES, "text/plain")
        _upload(client, token_b, "b_only.txt", TXT_BYTES, "text/plain")

        a_items = client.get(LIST_URL, **_auth(token_a)).json()
        b_items = client.get(LIST_URL, **_auth(token_b)).json()

        a_names = {d["original_name"] for d in a_items}
        b_names = {d["original_name"] for d in b_items}
        assert a_names == {"a_only.txt"}
        assert b_names == {"b_only.txt"}
        # No id overlap between the two users' lists.
        a_ids = {d["id"] for d in a_items}
        b_ids = {d["id"] for d in b_items}
        assert a_ids.isdisjoint(b_ids)


# ---------------------------------------------------------------------------
# Delete view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeleteView:
    def test_delete_own_doc_returns_204_and_removes_file(self) -> None:
        token = _register_and_login("edge_del_own@test.com")
        client = Client()
        resp = _upload(client, token, "del.txt", TXT_BYTES, "text/plain")
        doc_id = resp.json()["document_id"]
        path = Document.objects.get(pk=doc_id).file.path
        assert os.path.exists(path)

        resp = client.delete(f"/api/documents/{doc_id}/", **_auth(token))
        assert resp.status_code == 204
        assert not Document.objects.filter(pk=doc_id).exists()
        assert not os.path.exists(path)

    def test_delete_removes_from_list(self) -> None:
        token = _register_and_login("edge_del_list@test.com")
        client = Client()
        r1 = _upload(client, token, "keep.txt", TXT_BYTES, "text/plain")
        r2 = _upload(client, token, "drop.txt", TXT_BYTES, "text/plain")
        keep_id = r1.json()["document_id"]
        drop_id = r2.json()["document_id"]

        client.delete(f"/api/documents/{drop_id}/", **_auth(token))
        remaining = {d["id"] for d in client.get(LIST_URL, **_auth(token)).json()}
        assert remaining == {keep_id}

    def test_delete_nonexistent_id_returns_404(self) -> None:
        token = _register_and_login("edge_del_missing@test.com")
        client = Client()
        resp = client.delete("/api/documents/999999/", **_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_other_users_doc_returns_404_not_403(self) -> None:
        """Cross-user delete must be 404 (D-020) — no existence leak via 403."""
        token_a = _register_and_login("edge_del_a@test.com")
        token_b = _register_and_login("edge_del_b@test.com")
        client = Client()

        resp = _upload(client, token_a, "a_secret.txt", TXT_BYTES, "text/plain")
        doc_id_a = resp.json()["document_id"]

        # B tries to delete A's document.
        resp = client.delete(f"/api/documents/{doc_id_a}/", **_auth(token_b))
        assert resp.status_code == 404
        # A's document and its file must be untouched.
        doc = Document.objects.get(pk=doc_id_a)
        assert os.path.exists(doc.file.path)

    def test_delete_twice_second_is_404(self) -> None:
        token = _register_and_login("edge_del_twice@test.com")
        client = Client()
        resp = _upload(client, token, "once.txt", TXT_BYTES, "text/plain")
        doc_id = resp.json()["document_id"]

        first = client.delete(f"/api/documents/{doc_id}/", **_auth(token))
        assert first.status_code == 204
        second = client.delete(f"/api/documents/{doc_id}/", **_auth(token))
        assert second.status_code == 404
