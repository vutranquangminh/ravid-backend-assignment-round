"""Per-user ISOLATION matrix across the whole RAVID API.

Isolation is the single most important correctness property of the backend
(D-013, D-020, M-005): one user must never observe, mutate, or retrieve
another user's documents, ingestion jobs, or vectors.

This module sets up three users — A, B, and a brand-new C with no uploads —
and asserts isolation across every surface:

  documents list  — GET /api/documents/  shows ONLY the caller's own docs.
  delete          — DELETE /api/documents/<pk>/ is owner-scoped; cross-user → 404.
  status          — GET /api/documents/status/?task_id= is owner-scoped; cross → 404.
  vectors         — chunks live ONLY in user_<id>; queries never cross over;
                    delete empties the owner's vectors but leaves others intact.
  fresh user C    — empty list, empty/absent collection, 404 on others' task_ids.

All tests run offline & deterministically:
  - RAVID_EMBEDDINGS_STUB=True (config.settings.test) → deterministic stub vectors.
  - CHROMA_PERSIST_DIR is a temp dir.
  - CELERY_TASK_ALWAYS_EAGER=True → ingest_document runs synchronously on upload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from apps.rag import vectorstore
from apps.rag.embeddings import get_embeddings
from apps.rag.models import IngestionJob
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
UPLOAD_URL = "/api/documents/upload/"
LIST_URL = "/api/documents/"
STATUS_URL = "/api/documents/status/"


def _delete_url(pk: int) -> str:
    return f"/api/documents/{pk}/"


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------


# A TXT body large enough to produce at least one chunk per upload, with
# distinct content per user so we can prove vectors never cross collections.
def _txt_for(tag: str) -> bytes:
    return (
        f"Document owned by {tag}. "
        f"This is a plain-text document with enough words to produce at "
        f"least one chunk for user {tag}. Unique marker {tag}-{tag}-{tag}."
    ).encode()


_MD_CONTENT = b"# Heading\n\nThis markdown file has content that can be split and embedded."

# Valid PDF with extractable text ("Hello World"), reused from the ingestion tests.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


@dataclass
class Principal:
    """A registered+logged-in user with their JWT, model row, and uploads."""

    email: str
    token: str
    user_id: int
    # Mapping of label -> {"document_id", "task_id"} for each upload.
    uploads: dict

    def auth(self) -> dict:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}


def _register_and_login(email: str, password: str = "StrongPass1!") -> str:
    """Register a new user and return their JWT access token."""
    c = Client()
    reg = _post_json(c, REGISTER_URL, {"email": email, "password": password})
    assert reg.status_code == 201, f"Register failed: {reg.json()}"
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


def _make_principal(email: str, uploads: list[tuple] | None = None) -> Principal:
    """Register + login a user and run zero or more uploads.

    Args:
        email: the user's email (also the username).
        uploads: list of (label, filename, content, content_type) tuples.

    Returns:
        A ``Principal`` carrying the token, user_id, and an uploads map keyed
        by label → {"document_id", "task_id"}.
    """
    token = _register_and_login(email)
    user = User.objects.get(email=email)
    client = Client()
    upload_map: dict = {}
    for label, filename, content, content_type in uploads or []:
        resp = _upload(client, token, filename, content, content_type)
        assert resp.status_code == 202, f"Upload failed for {email}: {resp.json()}"
        body = resp.json()
        upload_map[label] = {
            "document_id": body["document_id"],
            "task_id": body["task_id"],
        }
    return Principal(email=email, token=token, user_id=user.pk, uploads=upload_map)


def _list_docs(client: Client, principal: Principal) -> list:
    resp = client.get(LIST_URL, **principal.auth())
    assert resp.status_code == 200
    return resp.json()


def _doc_ids(docs: list) -> set:
    return {d["id"] for d in docs}


def _vectors_for(owner_id: int, document_id: int) -> list:
    """Return the chroma ids of chunks for *document_id* in *owner_id*'s collection."""
    col = vectorstore.get_collection(owner_id)
    if col.count() == 0:
        return []
    return col.get(where={"document_id": str(document_id)})["ids"]


# ---------------------------------------------------------------------------
# Shared three-user fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def matrix(db) -> dict:
    """Three users: A (2 uploads), B (1 upload), C (no uploads)."""
    a = _make_principal(
        "iso_matrix_a@test.com",
        uploads=[
            ("txt", "a_doc.txt", _txt_for("AAA"), "text/plain"),
            ("md", "a_notes.md", _MD_CONTENT, "text/markdown"),
        ],
    )
    b = _make_principal(
        "iso_matrix_b@test.com",
        uploads=[
            ("pdf", "b_report.pdf", _PDF_WITH_TEXT, "application/pdf"),
        ],
    )
    c = _make_principal("iso_matrix_c@test.com", uploads=[])
    return {"a": a, "b": b, "c": c}


# ===========================================================================
# 1. DOCUMENTS LIST ISOLATION
# ===========================================================================


@pytest.mark.django_db
class TestDocumentListIsolation:
    def test_each_user_sees_only_own_documents(self, matrix: dict) -> None:
        a, b, c = matrix["a"], matrix["b"], matrix["c"]
        client = Client()

        a_docs = _list_docs(client, a)
        b_docs = _list_docs(client, b)
        c_docs = _list_docs(client, c)

        # Counts are independent.
        assert len(a_docs) == 2
        assert len(b_docs) == 1
        assert len(c_docs) == 0

        a_ids = _doc_ids(a_docs)
        b_ids = _doc_ids(b_docs)

        # A's list contains exactly A's two document ids.
        assert a_ids == {a.uploads["txt"]["document_id"], a.uploads["md"]["document_id"]}
        # B's list contains exactly B's one document id.
        assert b_ids == {b.uploads["pdf"]["document_id"]}
        # No overlap between A's and B's listings.
        assert a_ids.isdisjoint(b_ids)

    def test_a_cannot_see_b_document_in_list(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()

        a_ids = _doc_ids(_list_docs(client, a))
        b_doc_id = b.uploads["pdf"]["document_id"]
        assert b_doc_id not in a_ids

    def test_b_cannot_see_a_documents_in_list(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()

        b_ids = _doc_ids(_list_docs(client, b))
        for label in ("txt", "md"):
            assert a.uploads[label]["document_id"] not in b_ids

    def test_fresh_user_c_list_is_empty(self, matrix: dict) -> None:
        c = matrix["c"]
        client = Client()
        assert _list_docs(client, c) == []

    def test_list_count_unaffected_by_other_users_uploads(self, matrix: dict) -> None:
        """B uploading again must not change A's or C's counts."""
        a, b, c = matrix["a"], matrix["b"], matrix["c"]
        client = Client()

        # New upload by B.
        resp = _upload(client, b.token, "b_extra.txt", _txt_for("BBB"), "text/plain")
        assert resp.status_code == 202

        assert len(_list_docs(client, a)) == 2  # unchanged
        assert len(_list_docs(client, b)) == 2  # grew by one
        assert len(_list_docs(client, c)) == 0  # unchanged

    def test_list_requires_jwt(self) -> None:
        client = Client()
        resp = client.get(LIST_URL)
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_list_owned_doc_fields_belong_to_owner(self, matrix: dict) -> None:
        """Every doc returned to A names a file A actually uploaded."""
        a = matrix["a"]
        client = Client()
        docs = _list_docs(client, a)
        names = {d["original_name"] for d in docs}
        assert names == {"a_doc.txt", "a_notes.md"}


# ===========================================================================
# 2. DELETE ISOLATION
# ===========================================================================


@pytest.mark.django_db
class TestDeleteIsolation:
    def test_a_cannot_delete_b_document_returns_404(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()
        b_doc_id = b.uploads["pdf"]["document_id"]

        resp = client.delete(_delete_url(b_doc_id), **a.auth())
        assert resp.status_code == 404

    def test_failed_cross_delete_leaves_b_document_intact(self, matrix: dict) -> None:
        """A's 404 delete attempt must not remove B's document from B's list."""
        a, b = matrix["a"], matrix["b"]
        client = Client()
        b_doc_id = b.uploads["pdf"]["document_id"]

        resp = client.delete(_delete_url(b_doc_id), **a.auth())
        assert resp.status_code == 404

        # B still sees the document.
        assert b_doc_id in _doc_ids(_list_docs(client, b))

    def test_owner_can_delete_own_document(self, matrix: dict) -> None:
        a = matrix["a"]
        client = Client()
        doc_id = a.uploads["txt"]["document_id"]

        resp = client.delete(_delete_url(doc_id), **a.auth())
        assert resp.status_code == 204

        remaining = _doc_ids(_list_docs(client, a))
        assert doc_id not in remaining
        assert len(remaining) == 1  # the .md remains

    def test_delete_is_not_visible_to_other_users(self, matrix: dict) -> None:
        """A deleting A's doc must not change B's listing at all."""
        a, b = matrix["a"], matrix["b"]
        client = Client()
        before = _doc_ids(_list_docs(client, b))

        client.delete(_delete_url(a.uploads["md"]["document_id"]), **a.auth())

        after = _doc_ids(_list_docs(client, b))
        assert before == after

    def test_delete_nonexistent_pk_returns_404(self, matrix: dict) -> None:
        a = matrix["a"]
        client = Client()
        resp = client.delete(_delete_url(99_999_999), **a.auth())
        assert resp.status_code == 404

    def test_fresh_user_cannot_delete_any_existing_doc(self, matrix: dict) -> None:
        """C owns nothing; deleting A's or B's docs both 404."""
        a, b, c = matrix["a"], matrix["b"], matrix["c"]
        client = Client()

        for target in (
            a.uploads["txt"]["document_id"],
            a.uploads["md"]["document_id"],
            b.uploads["pdf"]["document_id"],
        ):
            resp = client.delete(_delete_url(target), **c.auth())
            assert resp.status_code == 404, f"C should not delete doc {target}"

    def test_delete_requires_jwt(self, matrix: dict) -> None:
        a = matrix["a"]
        client = Client()
        resp = client.delete(_delete_url(a.uploads["txt"]["document_id"]))
        assert resp.status_code == 401


# ===========================================================================
# 3. STATUS / TASK ISOLATION
# ===========================================================================


@pytest.mark.django_db
class TestStatusIsolation:
    def _status(self, client: Client, principal: Principal, task_id: str) -> object:
        return client.get(STATUS_URL, {"task_id": task_id}, **principal.auth())

    def test_owner_resolves_own_task(self, matrix: dict) -> None:
        a = matrix["a"]
        client = Client()
        task_id = a.uploads["txt"]["task_id"]
        resp = self._status(client, a, task_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == task_id
        assert body["status"] == "SUCCESS"

    def test_a_cannot_read_b_task_status_returns_404(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()
        b_task = b.uploads["pdf"]["task_id"]
        resp = self._status(client, a, b_task)
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_b_cannot_read_a_tasks_returns_404(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()
        for label in ("txt", "md"):
            resp = self._status(client, b, a.uploads[label]["task_id"])
            assert resp.status_code == 404

    def test_each_user_only_resolves_own_task_ids(self, matrix: dict) -> None:
        """Cross product: each user resolves only their own task_ids (200);
        every other user's task_id yields 404."""
        a, b, c = matrix["a"], matrix["b"], matrix["c"]
        client = Client()

        owned = {
            a.email: [a.uploads["txt"]["task_id"], a.uploads["md"]["task_id"]],
            b.email: [b.uploads["pdf"]["task_id"]],
            c.email: [],
        }
        principals = {a.email: a, b.email: b, c.email: c}

        all_task_ids = [tid for ids in owned.values() for tid in ids]
        for email, principal in principals.items():
            for task_id in all_task_ids:
                resp = self._status(client, principal, task_id)
                if task_id in owned[email]:
                    assert resp.status_code == 200, f"{email} should resolve own {task_id}"
                    assert resp.json()["task_id"] == task_id
                else:
                    assert resp.status_code == 404, f"{email} must NOT see {task_id}"

    def test_fresh_user_c_gets_404_on_every_other_task(self, matrix: dict) -> None:
        a, b, c = matrix["a"], matrix["b"], matrix["c"]
        client = Client()
        for task_id in (
            a.uploads["txt"]["task_id"],
            a.uploads["md"]["task_id"],
            b.uploads["pdf"]["task_id"],
        ):
            resp = self._status(client, c, task_id)
            assert resp.status_code == 404

    def test_unknown_task_id_returns_404(self, matrix: dict) -> None:
        a = matrix["a"]
        client = Client()
        resp = self._status(client, a, "definitely-not-a-real-task-id")
        assert resp.status_code == 404

    def test_status_requires_jwt(self, matrix: dict) -> None:
        a = matrix["a"]
        client = Client()
        resp = client.get(STATUS_URL, {"task_id": a.uploads["txt"]["task_id"]})
        assert resp.status_code == 401

    def test_status_owner_scoped_at_db_layer(self, matrix: dict) -> None:
        """Defense in depth: the IngestionJob query is owner-scoped, so B's
        own jobs never match A's task ids even at the model level."""
        a, b = matrix["a"], matrix["b"]
        b_task = b.uploads["pdf"]["task_id"]

        # The job exists globally...
        assert IngestionJob.objects.filter(celery_task_id=b_task).exists()
        # ...but not for owner A.
        assert not IngestionJob.objects.filter(celery_task_id=b_task, owner_id=a.user_id).exists()
        # ...and exactly for owner B.
        assert IngestionJob.objects.filter(celery_task_id=b_task, owner_id=b.user_id).exists()


# ===========================================================================
# 4. VECTOR ISOLATION
# ===========================================================================


@pytest.mark.django_db
class TestVectorIsolation:
    def test_chunks_live_only_in_owner_collection(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        a_txt = a.uploads["txt"]["document_id"]
        b_pdf = b.uploads["pdf"]["document_id"]

        # A's TXT chunks are in A's collection.
        assert len(_vectors_for(a.user_id, a_txt)) > 0
        # ...and NOT in B's collection.
        assert len(_vectors_for(b.user_id, a_txt)) == 0

        # B's PDF chunks are in B's collection.
        assert len(_vectors_for(b.user_id, b_pdf)) > 0
        # ...and NOT in A's collection.
        assert len(_vectors_for(a.user_id, b_pdf)) == 0

    def test_collection_names_are_per_user(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        col_a = vectorstore.get_collection(a.user_id)
        col_b = vectorstore.get_collection(b.user_id)
        assert col_a.name == f"user_{a.user_id}"
        assert col_b.name == f"user_{b.user_id}"
        assert col_a.name != col_b.name

    def test_all_metadata_document_ids_belong_to_owner(self, matrix: dict) -> None:
        """Every chunk metadata in A's collection references one of A's docs."""
        a = matrix["a"]
        a_doc_ids = {
            str(a.uploads["txt"]["document_id"]),
            str(a.uploads["md"]["document_id"]),
        }
        col_a = vectorstore.get_collection(a.user_id)
        got = col_a.get(include=["metadatas"])
        assert len(got["ids"]) > 0
        for md in got["metadatas"]:
            assert md["document_id"] in a_doc_ids

    def test_query_a_collection_never_returns_b_document_id(self, matrix: dict) -> None:
        """Querying A's collection with B's own document text never surfaces
        B's document_id (different collection entirely)."""
        a, b = matrix["a"], matrix["b"]
        b_pdf = str(b.uploads["pdf"]["document_id"])

        # Build a query embedding from B's content; query A's collection.
        emb = get_embeddings().embed_query("Hello World")
        result = vectorstore.query(a.user_id, emb, k=4)

        returned_doc_ids = {md["document_id"] for batch in result["metadatas"] for md in batch}
        assert b_pdf not in returned_doc_ids
        # And every returned id is one of A's.
        a_ids = {
            str(a.uploads["txt"]["document_id"]),
            str(a.uploads["md"]["document_id"]),
        }
        assert returned_doc_ids.issubset(a_ids)

    def test_query_respects_top_k_bound(self, matrix: dict) -> None:
        """vectorstore.query never returns more than k results (D-012/D-014)."""
        a = matrix["a"]
        emb = get_embeddings().embed_query("anything")
        result = vectorstore.query(a.user_id, emb, k=4)
        # One query batch; its id list is bounded by k.
        assert len(result["ids"]) == 1
        assert len(result["ids"][0]) <= 4

    def test_delete_a_doc_empties_a_vectors_leaves_b_intact(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()
        a_txt = a.uploads["txt"]["document_id"]
        b_pdf = b.uploads["pdf"]["document_id"]

        # Pre-conditions.
        assert len(_vectors_for(a.user_id, a_txt)) > 0
        b_vecs_before = _vectors_for(b.user_id, b_pdf)
        assert len(b_vecs_before) > 0

        # Delete A's TXT document.
        resp = client.delete(_delete_url(a_txt), **a.auth())
        assert resp.status_code == 204

        # A's TXT vectors gone...
        assert len(_vectors_for(a.user_id, a_txt)) == 0
        # ...but A's OTHER doc (md) vectors remain.
        assert len(_vectors_for(a.user_id, a.uploads["md"]["document_id"])) > 0
        # ...and B's vectors are completely untouched.
        assert _vectors_for(b.user_id, b_pdf) == b_vecs_before

    def test_delete_does_not_touch_other_user_collection_count(self, matrix: dict) -> None:
        a, b = matrix["a"], matrix["b"]
        client = Client()
        b_count_before = vectorstore.get_collection(b.user_id).count()

        client.delete(_delete_url(a.uploads["txt"]["document_id"]), **a.auth())

        assert vectorstore.get_collection(b.user_id).count() == b_count_before

    def test_fresh_user_collection_is_empty(self, matrix: dict) -> None:
        """C never uploaded → its collection (created lazily) holds zero vectors."""
        c = matrix["c"]
        col_c = vectorstore.get_collection(c.user_id)
        assert col_c.count() == 0

    def test_fresh_user_query_returns_nothing(self, matrix: dict) -> None:
        """Querying C's empty collection yields no documents/metadatas."""
        c = matrix["c"]
        emb = get_embeddings().embed_query("any question")
        result = vectorstore.query(c.user_id, emb, k=4)
        assert result["ids"][0] == []
        assert result["metadatas"][0] == []


# ===========================================================================
# 5. CROSS-CUTTING / TRUST-BOUNDARY MATRIX
# ===========================================================================


@pytest.mark.django_db
class TestTrustBoundaryMatrix:
    def test_register_a_login_b_grants_no_access_to_a(self) -> None:
        """Registering A then logging in as B never grants B access to A's
        documents, task status, or delete."""
        a = _make_principal(
            "trust_a@test.com",
            uploads=[("txt", "a_only.txt", _txt_for("ATRUST"), "text/plain")],
        )
        b = _make_principal("trust_b@test.com", uploads=[])
        client = Client()

        a_doc = a.uploads["txt"]["document_id"]
        a_task = a.uploads["txt"]["task_id"]

        # B cannot see A's doc in its list.
        assert a_doc not in _doc_ids(_list_docs(client, b))
        # B cannot read A's task status.
        assert client.get(STATUS_URL, {"task_id": a_task}, **b.auth()).status_code == 404
        # B cannot delete A's doc.
        assert client.delete(_delete_url(a_doc), **b.auth()).status_code == 404
        # B's own collection has no trace of A's vectors.
        assert len(_vectors_for(b.user_id, a_doc)) == 0
        # ...while A still owns and can see its document.
        assert a_doc in _doc_ids(_list_docs(client, a))

    def test_token_swap_does_not_widen_access(self, matrix: dict) -> None:
        """Using A's token only ever scopes to A; using B's token only to B.
        A request authenticated as A can never reach B's resources and vice
        versa across list, status, and delete simultaneously."""
        a, b = matrix["a"], matrix["b"]
        client = Client()

        a_doc = a.uploads["txt"]["document_id"]
        b_doc = b.uploads["pdf"]["document_id"]
        a_task = a.uploads["txt"]["task_id"]
        b_task = b.uploads["pdf"]["task_id"]

        # A's token: own ok, other 404/absent.
        assert a_doc in _doc_ids(_list_docs(client, a))
        assert b_doc not in _doc_ids(_list_docs(client, a))
        assert client.get(STATUS_URL, {"task_id": a_task}, **a.auth()).status_code == 200
        assert client.get(STATUS_URL, {"task_id": b_task}, **a.auth()).status_code == 404

        # B's token: own ok, other 404/absent.
        assert b_doc in _doc_ids(_list_docs(client, b))
        assert a_doc not in _doc_ids(_list_docs(client, b))
        assert client.get(STATUS_URL, {"task_id": b_task}, **b.auth()).status_code == 200
        assert client.get(STATUS_URL, {"task_id": a_task}, **b.auth()).status_code == 404

    def test_three_user_full_matrix_no_leakage(self, matrix: dict) -> None:
        """End-to-end: for all (viewer, owner) pairs, a viewer only ever sees
        the owner's documents/tasks/vectors when viewer == owner."""
        a, b, c = matrix["a"], matrix["b"], matrix["c"]
        client = Client()

        owned_docs = {
            a.email: {a.uploads["txt"]["document_id"], a.uploads["md"]["document_id"]},
            b.email: {b.uploads["pdf"]["document_id"]},
            c.email: set(),
        }
        principals = [a, b, c]
        all_docs = set().union(*owned_docs.values())

        for viewer in principals:
            visible = _doc_ids(_list_docs(client, viewer))
            # Viewer sees exactly their own docs.
            assert visible == owned_docs[viewer.email], f"{viewer.email} list leak"
            # Every doc the viewer does NOT own is invisible and undeletable.
            for doc_id in all_docs - owned_docs[viewer.email]:
                assert doc_id not in visible
                assert client.delete(_delete_url(doc_id), **viewer.auth()).status_code == 404
                # No vector trace of a non-owned doc in the viewer's collection.
                assert len(_vectors_for(viewer.user_id, doc_id)) == 0
