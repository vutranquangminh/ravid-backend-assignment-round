"""Edge-case integration tests for the RAG ingestion pipeline (slice 04).

Complements ``test_ingestion_api.py`` with deeper coverage of:
  - Chunking boundaries: multi-paragraph / long text → many chunks; single
    short doc → exactly one chunk; unicode/non-ascii ingests fine; the exact
    chunk_count matches the locked 1000/150 splitter (D-011).
  - Idempotent re-ingestion: re-running the same document (same chunk ids) does
    NOT double the owner's Chroma collection count (vectorstore upsert IDs are
    ``"<document_id>:<index>"``).
  - Status contract: SUCCESS body carries the EXACT message; constructed PENDING
    and STARTED jobs both map to PROCESSING; FAILURE → ``{status, error}``;
    missing task_id → 400; unknown task_id → 404; no token → 401.
  - Failure path via monkeypatch of ``apps.rag.pipeline.run_ingestion`` (and of
    ``extract_text``): the job is marked FAILURE with an error_message, the
    status endpoint reports FAILURE, the failure is LOGGED at ERROR (D-026) and
    the exception is NOT swallowed silently (it must surface somewhere).
  - IngestionJob model invariants: celery_task_id uniqueness, status choices,
    chunk_count default 0.

All tests are offline + deterministic:
  - RAVID_EMBEDDINGS_STUB=True (config.settings.test) → no model download.
  - CHROMA_PERSIST_DIR is a temp dir (config.settings.test).
  - CELERY_TASK_ALWAYS_EAGER=True → the ingest task runs synchronously in-process.
"""

from __future__ import annotations

import json
import logging

import pytest
from apps.rag.models import IngestionJob
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

UPLOAD_URL = "/api/documents/upload/"
STATUS_URL = "/api/documents/status/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"

SUCCESS_MESSAGE = "Document successfully parsed, embedded, and indexed in vector storage."

# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

# A valid PDF with extractable text ("Hello World") — reused from the existing
# ingestion tests so PDF extraction stays exercised offline.
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

# A short single-chunk document.
_SHORT_TXT = b"A short note that fits well within one thousand characters."

# Whitespace-separated long text. 100 reps of "lorem ipsum dolor sit amet "
# = 2700 chars which the 1000/150 RecursiveCharacterTextSplitter deterministically
# splits into exactly 3 chunks (verified against the real splitter).
_LONG_TXT_3_CHUNKS = (b"lorem ipsum dolor sit amet ") * 100

# Six paragraphs separated by blank lines (~3604 chars) → exactly 6 chunks.
_PARAGRAPH = (b"word " * 120).strip()
_MULTI_PARAGRAPH_6_CHUNKS = b"\n\n".join([_PARAGRAPH] * 6)

# Contiguous 1000 'y' chars → exactly 1 chunk (== chunk_size boundary).
_EXACTLY_1000 = b"y" * 1000
# Contiguous 1001 'z' chars → exactly 2 chunks (just over the boundary).
_OVER_1000 = b"z" * 1001

# Non-ascii / unicode content — must ingest without decode errors.
_UNICODE_TXT = "café déjà vu — 日本語 текст emoji 🚀 ".encode()


# ---------------------------------------------------------------------------
# Helpers (local to this file — no shared-module edits)
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _register_and_login(email: str, password: str = "StrongPass1!") -> str:
    """Register a fresh user and return their JWT access token."""
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


def _make_user(email: str, password: str = "pass12345") -> object:
    return User.objects.create_user(username=email, email=email, password=password)


def _make_document(user: object, name: str = "x.txt", content: bytes = b"content") -> object:
    """Create a stored Document row for *user* via the documents service."""
    from apps.documents.services import create_document  # noqa: PLC0415

    f = SimpleUploadedFile(name, content, content_type="text/plain")
    return create_document(owner=user, uploaded_file=f)


def _reset_collection(owner_id: int) -> None:
    """Drop the owner's Chroma collection for a clean per-test baseline.

    Chroma uses a single process-wide PersistentClient against one temp dir,
    while the in-memory sqlite DB resets pks every test — so collection
    ``user_<pk>`` can carry vectors from a prior test that reused the same pk.
    Tests asserting on ABSOLUTE counts (or absence) reset first; tests that scope
    to a specific document_id do not need this.
    """
    import contextlib  # noqa: PLC0415

    from apps.rag import vectorstore  # noqa: PLC0415

    client = vectorstore._client()
    # Collection may not exist yet — suppress chromadb's not-found error.
    with contextlib.suppress(Exception):
        client.delete_collection(f"user_{owner_id}")


# ---------------------------------------------------------------------------
# Chunking boundaries — exact chunk_count under the locked 1000/150 splitter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChunkingBoundaries:
    def test_short_doc_produces_exactly_one_chunk(self) -> None:
        """A doc well under chunk_size yields exactly one chunk (>= 1)."""
        token = _register_and_login("chunk_short@test.com")
        client = Client()

        up = _upload(client, token, "short.txt", _SHORT_TXT, "text/plain")
        assert up.status_code == 202
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count == 1

    def test_long_whitespace_text_produces_three_chunks(self) -> None:
        """2700-char whitespace text → exactly 3 chunks (1000/150 splitter)."""
        token = _register_and_login("chunk_long@test.com")
        client = Client()

        up = _upload(client, token, "long.txt", _LONG_TXT_3_CHUNKS, "text/plain")
        assert up.status_code == 202
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count == 3

    def test_multi_paragraph_text_produces_six_chunks(self) -> None:
        """Six blank-line-separated paragraphs → exactly 6 chunks."""
        token = _register_and_login("chunk_paras@test.com")
        client = Client()

        up = _upload(client, token, "paras.txt", _MULTI_PARAGRAPH_6_CHUNKS, "text/plain")
        assert up.status_code == 202
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count == 6

    def test_exactly_chunk_size_boundary_is_one_chunk(self) -> None:
        """Exactly 1000 contiguous chars sits on the boundary → one chunk."""
        token = _register_and_login("chunk_1000@test.com")
        client = Client()

        up = _upload(client, token, "thousand.txt", _EXACTLY_1000, "text/plain")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count == 1

    def test_one_over_chunk_size_boundary_is_two_chunks(self) -> None:
        """1001 contiguous chars crosses the boundary → two chunks."""
        token = _register_and_login("chunk_1001@test.com")
        client = Client()

        up = _upload(client, token, "over.txt", _OVER_1000, "text/plain")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count == 2

    def test_chunk_count_matches_chroma_vector_count(self) -> None:
        """The job's chunk_count equals the number of vectors actually upserted."""
        from apps.rag import vectorstore  # noqa: PLC0415

        token = _register_and_login("chunk_match@test.com")
        client = Client()
        user = User.objects.get(email="chunk_match@test.com")
        _reset_collection(user.pk)

        up = _upload(client, token, "match.txt", _LONG_TXT_3_CHUNKS, "text/plain")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        col = vectorstore.get_collection(user.pk)
        doc_vecs = col.get(where={"document_id": str(doc_id)})
        assert len(doc_vecs["ids"]) == job.chunk_count == 3


# ---------------------------------------------------------------------------
# Unicode / non-ascii
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUnicodeIngestion:
    def test_unicode_txt_ingests_successfully(self) -> None:
        """Non-ascii TXT ingests without a decode error → SUCCESS."""
        token = _register_and_login("uni_txt@test.com")
        client = Client()

        up = _upload(client, token, "unicode.txt", _UNICODE_TXT, "text/plain")
        assert up.status_code == 202
        task_id = up.json()["task_id"]

        resp = _get_status(client, token, task_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "SUCCESS"

    def test_unicode_md_produces_at_least_one_chunk(self) -> None:
        """Non-ascii markdown ingests and yields >= 1 chunk."""
        token = _register_and_login("uni_md@test.com")
        client = Client()

        content = ("# 見出し\n\nрусский текст with café accents. " * 3).encode()
        up = _upload(client, token, "uni.md", content, "text/markdown")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.SUCCESS
        assert job.chunk_count >= 1

    def test_unicode_content_preserved_in_chroma(self) -> None:
        """The stored chunk text in Chroma keeps the original unicode."""
        from apps.rag import vectorstore  # noqa: PLC0415

        token = _register_and_login("uni_store@test.com")
        client = Client()
        user = User.objects.get(email="uni_store@test.com")

        marker = "日本語テキスト сигнал café"
        up = _upload(client, token, "marker.txt", marker.encode(), "text/plain")
        doc_id = up.json()["document_id"]

        col = vectorstore.get_collection(user.pk)
        stored = col.get(where={"document_id": str(doc_id)}, include=["documents"])
        joined = " ".join(stored["documents"])
        assert marker in joined


# ---------------------------------------------------------------------------
# Idempotent re-ingestion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIdempotentReingestion:
    def test_reingesting_same_document_does_not_double_count(self) -> None:
        """Re-running the pipeline on the same document overwrites vectors.

        IDs are ``"<document_id>:<index>"``, so a second upsert of the same
        chunks must NOT increase the collection's vector count.
        """
        from apps.rag import pipeline, vectorstore  # noqa: PLC0415

        user = _make_user("reingest_count@test.com")
        _reset_collection(user.pk)
        doc = _make_document(user, "re.txt", _LONG_TXT_3_CHUNKS)
        job = IngestionJob.objects.create(owner=user, source_document=doc)

        first = pipeline.run_ingestion(job)
        col = vectorstore.get_collection(user.pk)
        count_after_first = col.count()
        assert first == 3
        assert count_after_first == 3

        second = pipeline.run_ingestion(job)
        # Refetch the collection handle to avoid any stale local cache.
        col = vectorstore.get_collection(user.pk)
        count_after_second = col.count()
        assert second == 3
        assert count_after_second == count_after_first, (
            "Re-ingesting the same document must not double the vector count"
        )

    def test_reingest_keeps_same_chunk_ids(self) -> None:
        """The deterministic ids are identical across re-ingestion runs."""
        from apps.rag import pipeline, vectorstore  # noqa: PLC0415

        user = _make_user("reingest_ids@test.com")
        _reset_collection(user.pk)
        doc = _make_document(user, "ids.txt", _LONG_TXT_3_CHUNKS)
        job = IngestionJob.objects.create(owner=user, source_document=doc)

        pipeline.run_ingestion(job)
        col = vectorstore.get_collection(user.pk)
        ids_first = sorted(col.get(where={"document_id": str(doc.pk)})["ids"])

        pipeline.run_ingestion(job)
        col = vectorstore.get_collection(user.pk)
        ids_second = sorted(col.get(where={"document_id": str(doc.pk)})["ids"])

        assert ids_first == ids_second
        assert ids_first == [f"{doc.pk}:0", f"{doc.pk}:1", f"{doc.pk}:2"]

    def test_reupload_via_api_creates_new_doc_but_isolated_ids(self) -> None:
        """Two API uploads of identical bytes get distinct document_ids.

        Each upload is a new Document (different pk), so their chunk ids do not
        collide and both sets of vectors coexist in the owner's collection.
        """
        from apps.rag import vectorstore  # noqa: PLC0415

        token = _register_and_login("reupload@test.com")
        client = Client()
        user = User.objects.get(email="reupload@test.com")
        _reset_collection(user.pk)

        up1 = _upload(client, token, "dup1.txt", _LONG_TXT_3_CHUNKS, "text/plain")
        up2 = _upload(client, token, "dup2.txt", _LONG_TXT_3_CHUNKS, "text/plain")
        doc1 = up1.json()["document_id"]
        doc2 = up2.json()["document_id"]
        assert doc1 != doc2

        col = vectorstore.get_collection(user.pk)
        assert len(col.get(where={"document_id": str(doc1)})["ids"]) == 3
        assert len(col.get(where={"document_id": str(doc2)})["ids"]) == 3
        assert col.count() == 6


# ---------------------------------------------------------------------------
# Status endpoint contract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStatusContract:
    def _token(self, email: str) -> str:
        c = Client()
        _post_json(c, REGISTER_URL, {"email": email, "password": "pass12345"})
        resp = _post_json(c, LOGIN_URL, {"email": email, "password": "pass12345"})
        return resp.json()["token"]

    def _job_for(self, email: str, status_val: str, error: str = "") -> object:
        user = _make_user(email)
        doc = _make_document(user)
        return IngestionJob.objects.create(
            owner=user,
            source_document=doc,
            status=status_val,
            celery_task_id=f"task-{email}",
            error_message=error,
        )

    def test_success_body_has_exact_message_and_keys(self) -> None:
        """SUCCESS body == {task_id, status, message} with the locked message."""
        job = self._job_for("ctr_success@test.com", "SUCCESS")
        token = self._token("ctr_success@test.com")
        resp = _get_status(Client(), token, job.celery_task_id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == job.celery_task_id
        assert body["status"] == "SUCCESS"
        assert body["message"] == SUCCESS_MESSAGE
        assert set(body.keys()) == {"task_id", "status", "message"}

    def test_pending_constructed_job_maps_to_processing(self) -> None:
        """A constructed PENDING job → PROCESSING (no message, no error)."""
        job = self._job_for("ctr_pending@test.com", "PENDING")
        token = self._token("ctr_pending@test.com")
        resp = _get_status(Client(), token, job.celery_task_id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "PROCESSING"
        assert "message" not in body
        assert "error" not in body
        assert set(body.keys()) == {"task_id", "status"}

    def test_started_constructed_job_maps_to_processing(self) -> None:
        """A constructed STARTED job also → PROCESSING."""
        job = self._job_for("ctr_started@test.com", "STARTED")
        token = self._token("ctr_started@test.com")
        resp = _get_status(Client(), token, job.celery_task_id)

        assert resp.status_code == 200
        assert resp.json()["status"] == "PROCESSING"

    def test_failure_job_returns_status_and_error(self) -> None:
        """A FAILURE job → {task_id, status: FAILURE, error: <msg>}."""
        job = self._job_for("ctr_fail@test.com", "FAILURE", error="boom happened")
        token = self._token("ctr_fail@test.com")
        resp = _get_status(Client(), token, job.celery_task_id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "FAILURE"
        assert body["error"] == "boom happened"
        assert set(body.keys()) == {"task_id", "status", "error"}

    def test_missing_task_id_param_returns_400_envelope(self) -> None:
        """No task_id query param → 400 single-key error envelope."""
        token = self._token("ctr_missing@test.com")
        resp = Client().get(STATUS_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        assert resp.status_code == 400
        body = resp.json()
        assert list(body.keys()) == ["error"]
        assert isinstance(body["error"], str)

    def test_blank_task_id_param_returns_400(self) -> None:
        """A whitespace-only task_id is treated as missing → 400."""
        token = self._token("ctr_blank@test.com")
        resp = _get_status(Client(), token, "   ")

        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_unknown_task_id_returns_404_envelope(self) -> None:
        """An unknown task_id → 404 single-key error envelope."""
        token = self._token("ctr_unknown@test.com")
        resp = _get_status(Client(), token, "does-not-exist-12345")

        assert resp.status_code == 404
        body = resp.json()
        assert list(body.keys()) == ["error"]

    def test_no_token_returns_401(self) -> None:
        """No JWT on the protected status route → 401."""
        resp = Client().get(STATUS_URL, {"task_id": "whatever"})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self) -> None:
        """A malformed bearer token → 401, not 200/404."""
        resp = Client().get(
            STATUS_URL,
            {"task_id": "whatever"},
            HTTP_AUTHORIZATION="Bearer not-a-real-jwt",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Per-user isolation on the status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStatusIsolation:
    def test_other_user_sees_404_for_foreign_task_id(self) -> None:
        """User B querying user A's (existing) task_id → 404, not 403/200."""
        token_a = _register_and_login("iso_status_a@test.com")
        token_b = _register_and_login("iso_status_b@test.com")
        client = Client()

        up = _upload(client, token_a, "a.txt", _SHORT_TXT, "text/plain")
        task_id_a = up.json()["task_id"]

        # Owner A can read it.
        own = _get_status(client, token_a, task_id_a)
        assert own.status_code == 200

        # B cannot — existence is hidden behind a 404 (D-020).
        foreign = _get_status(client, token_b, task_id_a)
        assert foreign.status_code == 404

    def test_two_users_same_taskid_value_are_distinct_rows(self) -> None:
        """A status lookup is scoped by owner, never leaking another user's job.

        celery_task_id is globally unique, so two users cannot share one; this
        verifies the owner filter is applied (B's own job is reachable, A's is
        not visible to B even though both exist).
        """
        user_a = _make_user("scope_a@test.com")
        user_b = _make_user("scope_b@test.com")
        doc_a = _make_document(user_a)
        doc_b = _make_document(user_b)
        IngestionJob.objects.create(
            owner=user_a, source_document=doc_a, status="SUCCESS", celery_task_id="task-A"
        )
        job_b = IngestionJob.objects.create(
            owner=user_b, source_document=doc_b, status="SUCCESS", celery_task_id="task-B"
        )

        c = Client()
        _post_json(c, REGISTER_URL, {"email": "scope_b@test.com", "password": "pass12345"})
        resp_b = _post_json(c, LOGIN_URL, {"email": "scope_b@test.com", "password": "pass12345"})
        token_b = resp_b.json()["token"]

        # B reads B's job fine.
        assert _get_status(Client(), token_b, job_b.celery_task_id).status_code == 200
        # B cannot read A's job.
        assert _get_status(Client(), token_b, "task-A").status_code == 404


# ---------------------------------------------------------------------------
# Failure path via monkeypatch — surfaced + logged + not swallowed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPipelineFailureSurfaced:
    def test_run_ingestion_raises_marks_job_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If run_ingestion raises, the job row becomes FAILURE + error_message."""
        import apps.rag.pipeline as pipeline_mod  # noqa: PLC0415

        def _boom(_job: object) -> int:
            raise RuntimeError("embedding backend exploded")

        monkeypatch.setattr(pipeline_mod, "run_ingestion", _boom)

        token = _register_and_login("fail_run@test.com")
        client = Client()
        up = _upload(client, token, "fail.txt", _SHORT_TXT, "text/plain")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.FAILURE
        assert "embedding backend exploded" in job.error_message

    def test_failure_status_endpoint_reports_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A monkeypatched failure is reflected through the status endpoint."""
        import apps.rag.pipeline as pipeline_mod  # noqa: PLC0415

        def _boom(_job: object) -> int:
            raise RuntimeError("upsert rejected")

        monkeypatch.setattr(pipeline_mod, "run_ingestion", _boom)

        token = _register_and_login("fail_status@test.com")
        client = Client()
        up = _upload(client, token, "fs.txt", _SHORT_TXT, "text/plain")
        task_id = up.json()["task_id"]

        resp = _get_status(client, token, task_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "FAILURE"
        assert "upsert rejected" in body["error"]

    def test_failure_is_logged_at_error_and_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The failure must be LOGGED at ERROR on apps.rag.tasks (D-026).

        'Not swallowed' here means it is surfaced: an ERROR record is emitted
        and the job row carries the error — the failure does not vanish.
        """
        import apps.rag.pipeline as pipeline_mod  # noqa: PLC0415

        def _boom(_job: object) -> int:
            raise RuntimeError("parser crashed hard")

        monkeypatch.setattr(pipeline_mod, "run_ingestion", _boom)

        token = _register_and_login("fail_log@test.com")
        client = Client()
        with caplog.at_level(logging.ERROR, logger="apps.rag.tasks"):
            up = _upload(client, token, "fl.txt", _SHORT_TXT, "text/plain")
        doc_id = up.json()["document_id"]

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "Expected an ERROR log record for the failed ingestion"

        # The job row is also updated — the failure surfaced in BOTH places.
        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.FAILURE

    def test_extract_text_raising_propagates_to_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure deeper in the pipeline (extract_text) also marks FAILURE.

        run_ingestion calls the module-level extract_text, so patching it here
        exercises the real run_ingestion error path (not just the task wrapper).
        """
        import apps.rag.pipeline as pipeline_mod  # noqa: PLC0415

        def _bad_extract(_path: str, _ct: str) -> str:
            raise OSError("cannot read file from disk")

        monkeypatch.setattr(pipeline_mod, "extract_text", _bad_extract)

        token = _register_and_login("fail_extract@test.com")
        client = Client()
        up = _upload(client, token, "fe.txt", _SHORT_TXT, "text/plain")
        task_id = up.json()["task_id"]
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.FAILURE
        assert "cannot read file from disk" in job.error_message

        resp = _get_status(client, token, task_id)
        assert resp.json()["status"] == "FAILURE"

    def test_error_message_truncated_to_500_chars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The task stores at most 500 chars of the error message."""
        import apps.rag.pipeline as pipeline_mod  # noqa: PLC0415

        long_reason = "X" * 2000

        def _boom(_job: object) -> int:
            raise RuntimeError(long_reason)

        monkeypatch.setattr(pipeline_mod, "run_ingestion", _boom)

        token = _register_and_login("fail_trunc@test.com")
        client = Client()
        up = _upload(client, token, "ft.txt", _SHORT_TXT, "text/plain")
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.FAILURE
        assert len(job.error_message) == 500

    def test_failure_does_not_write_vectors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failed run must not leave partial vectors in the user's collection."""
        import apps.rag.pipeline as pipeline_mod  # noqa: PLC0415
        from apps.rag import vectorstore  # noqa: PLC0415

        def _boom(_job: object) -> int:
            raise RuntimeError("failed before upsert")

        monkeypatch.setattr(pipeline_mod, "run_ingestion", _boom)

        token = _register_and_login("fail_novec@test.com")
        client = Client()
        user = User.objects.get(email="fail_novec@test.com")
        _reset_collection(user.pk)
        up = _upload(client, token, "fnv.txt", _LONG_TXT_3_CHUNKS, "text/plain")
        doc_id = up.json()["document_id"]

        col = vectorstore.get_collection(user.pk)
        assert len(col.get(where={"document_id": str(doc_id)})["ids"]) == 0


# ---------------------------------------------------------------------------
# Empty / whitespace document → ValueError from the real pipeline
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmptyDocumentFailure:
    def test_whitespace_only_doc_fails_with_message(self) -> None:
        """A whitespace-only doc raises the 'No extractable text' guard → FAILURE."""
        token = _register_and_login("empty_ws@test.com")
        client = Client()

        up = _upload(client, token, "ws.txt", b"   \n\t  ", "text/plain")
        task_id = up.json()["task_id"]
        doc_id = up.json()["document_id"]

        job = IngestionJob.objects.get(source_document_id=doc_id)
        assert job.status == IngestionJob.Status.FAILURE
        assert "No extractable text" in job.error_message

        resp = _get_status(client, token, task_id)
        assert resp.json()["status"] == "FAILURE"

    def test_run_ingestion_raises_valueerror_on_empty_text(self) -> None:
        """Direct call: run_ingestion raises ValueError for empty text."""
        from apps.rag import pipeline  # noqa: PLC0415

        user = _make_user("empty_direct@test.com")
        doc = _make_document(user, "blank.txt", b"\n\n   \t ")
        job = IngestionJob.objects.create(owner=user, source_document=doc)

        with pytest.raises(ValueError, match="No extractable text"):
            pipeline.run_ingestion(job)


# ---------------------------------------------------------------------------
# IngestionJob model invariants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIngestionJobModel:
    def test_default_status_is_pending(self) -> None:
        """A freshly created job defaults to PENDING."""
        user = _make_user("model_default_status@test.com")
        doc = _make_document(user)
        job = IngestionJob.objects.create(owner=user, source_document=doc)
        assert job.status == IngestionJob.Status.PENDING

    def test_default_chunk_count_is_zero(self) -> None:
        """chunk_count defaults to 0 before the pipeline runs."""
        user = _make_user("model_chunk0@test.com")
        doc = _make_document(user)
        job = IngestionJob.objects.create(owner=user, source_document=doc)
        assert job.chunk_count == 0

    def test_default_error_message_is_empty_string(self) -> None:
        """error_message defaults to an empty string, never None."""
        user = _make_user("model_err_empty@test.com")
        doc = _make_document(user)
        job = IngestionJob.objects.create(owner=user, source_document=doc)
        assert job.error_message == ""

    def test_celery_task_id_nullable_until_dispatch(self) -> None:
        """celery_task_id may be null before .delay() returns."""
        user = _make_user("model_null_task@test.com")
        doc = _make_document(user)
        job = IngestionJob.objects.create(owner=user, source_document=doc)
        assert job.celery_task_id is None

    def test_celery_task_id_is_unique(self) -> None:
        """Two jobs cannot share a celery_task_id (DB-level uniqueness)."""
        user = _make_user("model_unique@test.com")
        doc1 = _make_document(user, "u1.txt")
        doc2 = _make_document(user, "u2.txt")
        IngestionJob.objects.create(owner=user, source_document=doc1, celery_task_id="shared-id")
        with pytest.raises(IntegrityError), transaction.atomic():
            IngestionJob.objects.create(
                owner=user, source_document=doc2, celery_task_id="shared-id"
            )

    def test_multiple_null_celery_task_ids_allowed(self) -> None:
        """Uniqueness must not reject multiple NULL celery_task_id rows."""
        user = _make_user("model_multi_null@test.com")
        doc1 = _make_document(user, "n1.txt")
        doc2 = _make_document(user, "n2.txt")
        IngestionJob.objects.create(owner=user, source_document=doc1)
        IngestionJob.objects.create(owner=user, source_document=doc2)
        assert IngestionJob.objects.filter(owner=user, celery_task_id__isnull=True).count() == 2

    def test_status_choices_are_the_locked_set(self) -> None:
        """The model exposes exactly PENDING/STARTED/SUCCESS/FAILURE."""
        values = {value for value, _label in IngestionJob.Status.choices}
        assert values == {"PENDING", "STARTED", "SUCCESS", "FAILURE"}

    def test_str_includes_owner_doc_and_status(self) -> None:
        """__str__ summarises owner, document, and status for logs."""
        user = _make_user("model_str@test.com")
        doc = _make_document(user)
        job = IngestionJob.objects.create(owner=user, source_document=doc, status="SUCCESS")
        rendered = str(job)
        assert f"owner={user.pk}" in rendered
        assert f"doc={doc.pk}" in rendered
        assert "status=SUCCESS" in rendered

    def test_owner_cascade_delete_removes_jobs(self) -> None:
        """Deleting the owner cascades to their ingestion jobs."""
        user = _make_user("model_cascade@test.com")
        doc = _make_document(user)
        job = IngestionJob.objects.create(owner=user, source_document=doc)
        job_pk = job.pk
        user.delete()
        assert not IngestionJob.objects.filter(pk=job_pk).exists()

    def test_jobs_ordered_newest_first(self) -> None:
        """Default ordering is most-recent-first (Meta.ordering = -created_at)."""
        user = _make_user("model_order@test.com")
        doc = _make_document(user)
        first = IngestionJob.objects.create(owner=user, source_document=doc)
        second = IngestionJob.objects.create(owner=user, source_document=doc)
        ordered = list(IngestionJob.objects.filter(owner=user))
        # Newest (second) appears before the older (first).
        assert ordered.index(second) < ordered.index(first)
