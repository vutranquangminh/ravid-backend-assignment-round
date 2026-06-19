"""Unit tests for the low-level RAG building blocks (slice 04).

Targets the three pure-ish modules — exercised entirely OFFLINE:
  - ``apps.rag.embeddings``   — the deterministic stub embedder.
  - ``apps.rag.vectorstore``  — per-user Chroma collections, upsert/query/delete.
  - ``apps.rag.pipeline``     — extract_text + run_ingestion.

Offline guarantees (all from ``config.settings.test``):
  - ``RAVID_EMBEDDINGS_STUB=True`` → ``get_embeddings()`` returns the 32-dim stub;
    no model download, no network (D-027).
  - ``CHROMA_PERSIST_DIR`` is a temp dir → a real (but throwaway) Chroma store.
  - No Celery / no DB needed for most of these: ``run_ingestion`` is driven with a
    tiny fake job object so the pipeline can be tested in isolation.

Collection-isolation note: the Chroma store is shared for the whole test session,
so each test that writes vectors uses its own unique owner id (via ``_uid()``)
to avoid cross-test bleed.  This mirrors the production "one collection per user"
boundary (D-013, M-005) while keeping tests independent.
"""

from __future__ import annotations

import itertools
import os
import tempfile

import pytest
from apps.rag import pipeline, vectorstore
from apps.rag.embeddings import _StubEmbeddings, get_embeddings
from django.conf import settings

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

STUB_DIM = 32  # _StubEmbeddings fixed dimensionality (embeddings._STUB_DIM)

# A counter that hands out unique owner ids so concurrent tests never collide
# inside the shared session-scoped Chroma store.  Start high to avoid clashing
# with any real user PKs created by other (DB-backed) suites.
_owner_counter = itertools.count(900_000)


def _uid() -> int:
    """Return a process-unique owner id for collection isolation."""
    return next(_owner_counter)


# A minimal PDF carrying the extractable text "Hello World".  Reused verbatim
# from the ingestion integration suite (pypdf is lenient about the xref offset).
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


def _write_temp(content: bytes | str, suffix: str) -> str:
    """Write *content* to a unique temp file and return its absolute path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"
    with open(path, mode, encoding=encoding) as fh:
        fh.write(content)
    return path


class _FakeFile:
    """Stand-in for ``Document.file`` exposing only ``.path``."""

    def __init__(self, path: str) -> None:
        self.path = path


class _FakeDocument:
    """Stand-in for a ``Document`` row — only the attrs run_ingestion reads."""

    def __init__(self, path: str, content_type: str) -> None:
        self.file = _FakeFile(path)
        self.content_type = content_type


class _FakeJob:
    """Minimal duck-typed ``IngestionJob`` for ``run_ingestion`` (no DB)."""

    def __init__(self, owner_id: int, document_id: int, path: str, content_type: str) -> None:
        self.owner_id = owner_id
        self.source_document_id = document_id
        self.source_document = _FakeDocument(path, content_type)


def _make_job(content: bytes | str, suffix: str, content_type: str) -> _FakeJob:
    """Build a fake ingestion job backed by a real temp file."""
    path = _write_temp(content, suffix)
    return _FakeJob(_uid(), document_id=_uid(), path=path, content_type=content_type)


# ===========================================================================
# embeddings.py
# ===========================================================================


class TestGetEmbeddingsFactory:
    def test_returns_stub_under_stub_flag(self) -> None:
        """RAVID_EMBEDDINGS_STUB is True in test settings → stub instance."""
        assert settings.RAVID_EMBEDDINGS_STUB is True
        emb = get_embeddings()
        assert isinstance(emb, _StubEmbeddings)

    def test_returns_stub_when_flag_explicitly_set(self, settings) -> None:
        """Explicit True flag still yields the stub (no model download)."""
        settings.RAVID_EMBEDDINGS_STUB = True
        assert isinstance(get_embeddings(), _StubEmbeddings)

    def test_no_network_no_real_model(self) -> None:
        """The stub exposes the LangChain embedder interface, no HF object."""
        emb = get_embeddings()
        assert hasattr(emb, "embed_documents")
        assert hasattr(emb, "embed_query")
        assert type(emb).__name__ == "_StubEmbeddings"


class TestStubEmbedDocuments:
    def test_one_vector_per_document(self) -> None:
        emb = _StubEmbeddings()
        vecs = emb.embed_documents(["a", "b", "c", "d"])
        assert len(vecs) == 4

    def test_each_vector_has_fixed_dim(self) -> None:
        emb = _StubEmbeddings()
        for v in emb.embed_documents(["alpha", "beta", "gamma"]):
            assert len(v) == STUB_DIM

    def test_empty_list_returns_empty(self) -> None:
        assert _StubEmbeddings().embed_documents([]) == []

    def test_single_element_list(self) -> None:
        vecs = _StubEmbeddings().embed_documents(["solo"])
        assert len(vecs) == 1
        assert len(vecs[0]) == STUB_DIM

    def test_deterministic_same_text_same_vector(self) -> None:
        """Same input text → byte-identical vector (idempotent / offline)."""
        emb = _StubEmbeddings()
        first = emb.embed_documents(["repeatable text"])[0]
        second = emb.embed_documents(["repeatable text"])[0]
        assert first == second

    def test_different_text_different_vector(self) -> None:
        emb = _StubEmbeddings()
        [va] = emb.embed_documents(["totally different one"])
        [vb] = emb.embed_documents(["a wholly distinct other"])
        assert va != vb

    def test_duplicate_inputs_yield_identical_vectors(self) -> None:
        """Repeated text inside one call maps to the same vector each time."""
        emb = _StubEmbeddings()
        vecs = emb.embed_documents(["same", "other", "same"])
        assert vecs[0] == vecs[2]
        assert vecs[0] != vecs[1]

    def test_all_components_finite(self) -> None:
        """No NaN / Inf — L2 normalisation is always safe (byte-derived)."""
        import math

        for v in _StubEmbeddings().embed_documents(["finite check", "another"]):
            assert all(math.isfinite(x) for x in v)

    def test_vectors_are_l2_normalised(self) -> None:
        """The stub L2-normalises so cosine similarity behaves correctly."""
        [v] = _StubEmbeddings().embed_documents(["normalise me please"])
        norm = sum(x * x for x in v) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-9)

    def test_unicode_text_supported(self) -> None:
        """Non-ASCII text embeds without error and stays fixed-dim."""
        [v] = _StubEmbeddings().embed_documents(["héllo 日本語 ünïcode 🚀"])
        assert len(v) == STUB_DIM

    def test_empty_string_document_has_fixed_dim(self) -> None:
        """An empty string is still a valid (fixed-dim) document vector."""
        [v] = _StubEmbeddings().embed_documents([""])
        assert len(v) == STUB_DIM


class TestStubEmbedQuery:
    def test_returns_single_vector(self) -> None:
        v = _StubEmbeddings().embed_query("a query")
        assert isinstance(v, list)
        assert all(isinstance(x, float) for x in v)

    def test_query_dim_matches_document_dim(self) -> None:
        emb = _StubEmbeddings()
        q = emb.embed_query("shared text")
        [d] = emb.embed_documents(["shared text"])
        assert len(q) == len(d) == STUB_DIM

    def test_query_matches_document_for_same_text(self) -> None:
        """embed_query and embed_documents agree for identical text."""
        emb = _StubEmbeddings()
        q = emb.embed_query("congruent")
        [d] = emb.embed_documents(["congruent"])
        assert q == d

    def test_query_deterministic(self) -> None:
        emb = _StubEmbeddings()
        assert emb.embed_query("stable") == emb.embed_query("stable")

    def test_different_queries_differ(self) -> None:
        emb = _StubEmbeddings()
        assert emb.embed_query("one") != emb.embed_query("two")

    def test_query_is_l2_normalised(self) -> None:
        v = _StubEmbeddings().embed_query("unit length")
        assert sum(x * x for x in v) ** 0.5 == pytest.approx(1.0, abs=1e-9)


# ===========================================================================
# vectorstore.py
# ===========================================================================


class TestGetCollection:
    def test_collection_named_for_owner(self) -> None:
        owner = _uid()
        col = vectorstore.get_collection(owner)
        assert col.name == f"user_{owner}"

    def test_same_owner_returns_same_collection(self) -> None:
        owner = _uid()
        a = vectorstore.get_collection(owner)
        b = vectorstore.get_collection(owner)
        assert a.name == b.name

    def test_two_owners_get_distinct_collections(self) -> None:
        o1, o2 = _uid(), _uid()
        c1 = vectorstore.get_collection(o1)
        c2 = vectorstore.get_collection(o2)
        assert c1.name != c2.name
        assert c1.name == f"user_{o1}"
        assert c2.name == f"user_{o2}"

    def test_idempotent_create(self) -> None:
        """Calling get_collection twice does not error or duplicate."""
        owner = _uid()
        vectorstore.get_collection(owner)
        # Second call must not raise and must keep count stable at zero.
        assert vectorstore.get_collection(owner).count() == 0


class TestUpsertChunks:
    def test_ids_follow_doc_index_pattern(self) -> None:
        owner, doc = _uid(), 77
        emb = get_embeddings()
        texts = ["x", "y", "z"]
        vectorstore.upsert_chunks(owner, doc, texts, emb.embed_documents(texts))
        got = vectorstore.get_collection(owner).get()
        assert set(got["ids"]) == {"77:0", "77:1", "77:2"}

    def test_metadata_carries_document_id_and_chunk_index(self) -> None:
        owner, doc = _uid(), 5
        emb = get_embeddings()
        texts = ["first", "second"]
        vectorstore.upsert_chunks(owner, doc, texts, emb.embed_documents(texts))
        got = vectorstore.get_collection(owner).get(ids=["5:0", "5:1"])
        metas = {m["chunk_index"]: m for m in got["metadatas"]}
        assert metas[0] == {"document_id": "5", "chunk_index": 0}
        assert metas[1] == {"document_id": "5", "chunk_index": 1}

    def test_document_id_stored_as_string(self) -> None:
        owner, doc = _uid(), 42
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner, doc, ["t"], emb.embed_documents(["t"]))
        meta = vectorstore.get_collection(owner).get(ids=["42:0"])["metadatas"][0]
        assert meta["document_id"] == "42"
        assert isinstance(meta["document_id"], str)

    def test_documents_text_round_trips(self) -> None:
        owner, doc = _uid(), 3
        emb = get_embeddings()
        texts = ["alpha text", "beta text"]
        vectorstore.upsert_chunks(owner, doc, texts, emb.embed_documents(texts))
        got = vectorstore.get_collection(owner).get(ids=["3:0", "3:1"])
        stored = dict(zip(got["ids"], got["documents"], strict=True))
        assert stored == {"3:0": "alpha text", "3:1": "beta text"}

    def test_count_equals_number_of_chunks(self) -> None:
        owner, doc = _uid(), 1
        emb = get_embeddings()
        texts = [f"chunk-{i}" for i in range(6)]
        vectorstore.upsert_chunks(owner, doc, texts, emb.embed_documents(texts))
        assert vectorstore.get_collection(owner).count() == 6

    def test_empty_texts_is_noop(self) -> None:
        """Upserting an empty list must not create/populate the collection."""
        owner = _uid()
        vectorstore.upsert_chunks(owner, 1, [], [])
        assert vectorstore.get_collection(owner).count() == 0

    def test_reupsert_same_ids_is_idempotent(self) -> None:
        """Re-ingesting the same document overwrites rather than duplicates."""
        owner, doc = _uid(), 9
        emb = get_embeddings()
        texts = ["v1-a", "v1-b"]
        vectorstore.upsert_chunks(owner, doc, texts, emb.embed_documents(texts))
        new_texts = ["v2-a", "v2-b"]
        vectorstore.upsert_chunks(owner, doc, new_texts, emb.embed_documents(new_texts))
        col = vectorstore.get_collection(owner)
        assert col.count() == 2  # not 4
        got = col.get(ids=["9:0", "9:1"])
        stored = dict(zip(got["ids"], got["documents"], strict=True))
        assert stored == {"9:0": "v2-a", "9:1": "v2-b"}

    def test_multiple_documents_coexist_in_one_collection(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner, 100, ["a"], emb.embed_documents(["a"]))
        vectorstore.upsert_chunks(owner, 200, ["b", "c"], emb.embed_documents(["b", "c"]))
        col = vectorstore.get_collection(owner)
        assert col.count() == 3
        assert {m["document_id"] for m in col.get()["metadatas"]} == {"100", "200"}


class TestQuery:
    def test_returns_expected_keys(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        texts = ["one", "two", "three"]
        vectorstore.upsert_chunks(owner, 1, texts, emb.embed_documents(texts))
        res = vectorstore.query(owner, emb.embed_query("one"), 2)
        for key in ("ids", "documents", "metadatas", "distances"):
            assert key in res

    def test_returns_up_to_k_results(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        texts = [f"doc-{i}" for i in range(10)]
        vectorstore.upsert_chunks(owner, 1, texts, emb.embed_documents(texts))
        res = vectorstore.query(owner, emb.embed_query("doc-0"), 4)
        assert len(res["ids"][0]) == 4

    def test_k_larger_than_count_caps_at_count(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        texts = ["a", "b", "c"]
        vectorstore.upsert_chunks(owner, 1, texts, emb.embed_documents(texts))
        res = vectorstore.query(owner, emb.embed_query("a"), 100)
        assert len(res["ids"][0]) == 3

    def test_k_one_returns_single_result(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        texts = ["a", "b", "c"]
        vectorstore.upsert_chunks(owner, 1, texts, emb.embed_documents(texts))
        res = vectorstore.query(owner, emb.embed_query("a"), 1)
        assert len(res["ids"][0]) == 1

    def test_query_on_empty_collection_returns_no_results(self) -> None:
        """An empty collection yields an empty result list (no crash)."""
        owner = _uid()
        emb = get_embeddings()
        res = vectorstore.query(owner, emb.embed_query("anything"), 4)
        assert res["ids"] == [[]]
        assert res["documents"] == [[]]

    def test_nearest_neighbour_is_exact_match(self) -> None:
        """Querying with a stored chunk's own text ranks it first (cosine)."""
        owner = _uid()
        emb = get_embeddings()
        texts = ["needle in haystack", "completely unrelated", "another filler"]
        vectorstore.upsert_chunks(owner, 1, texts, emb.embed_documents(texts))
        res = vectorstore.query(owner, emb.embed_query("needle in haystack"), 3)
        assert res["documents"][0][0] == "needle in haystack"

    def test_query_scoped_to_owner_collection(self) -> None:
        """A query on owner A never returns owner B's documents (D-013)."""
        owner_a, owner_b = _uid(), _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner_a, 1, ["A only text"], emb.embed_documents(["A only text"]))
        vectorstore.upsert_chunks(owner_b, 1, ["B only text"], emb.embed_documents(["B only text"]))
        res = vectorstore.query(owner_a, emb.embed_query("B only text"), 4)
        returned = res["documents"][0]
        assert "B only text" not in returned
        assert returned == ["A only text"]


class TestDeleteDocumentVectors:
    def test_removes_only_target_document(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner, 1, ["keep-a", "keep-b"], emb.embed_documents(["a", "b"]))
        vectorstore.upsert_chunks(owner, 2, ["drop-a", "drop-b"], emb.embed_documents(["c", "d"]))
        vectorstore.delete_document_vectors(owner, 2)
        col = vectorstore.get_collection(owner)
        remaining = {m["document_id"] for m in col.get()["metadatas"]}
        assert remaining == {"1"}
        assert col.count() == 2

    def test_removes_all_chunks_of_target(self) -> None:
        owner = _uid()
        emb = get_embeddings()
        texts = [f"c{i}" for i in range(5)]
        vectorstore.upsert_chunks(owner, 7, texts, emb.embed_documents(texts))
        vectorstore.delete_document_vectors(owner, 7)
        got = vectorstore.get_collection(owner).get(where={"document_id": "7"})
        assert got["ids"] == []

    def test_safe_when_document_not_present(self) -> None:
        """Deleting a doc with no vectors must not raise or affect others."""
        owner = _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner, 1, ["x"], emb.embed_documents(["x"]))
        vectorstore.delete_document_vectors(owner, 99999)  # never ingested
        assert vectorstore.get_collection(owner).count() == 1

    def test_safe_when_collection_absent(self) -> None:
        """Deleting from a never-created collection is a quiet no-op."""
        owner = _uid()  # collection has never been touched
        # Must not raise.
        vectorstore.delete_document_vectors(owner, 1)

    def test_delete_does_not_touch_other_owner(self) -> None:
        """Deleting owner A's doc leaves owner B's identical doc id intact."""
        owner_a, owner_b = _uid(), _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner_a, 5, ["a-text"], emb.embed_documents(["a-text"]))
        vectorstore.upsert_chunks(owner_b, 5, ["b-text"], emb.embed_documents(["b-text"]))
        vectorstore.delete_document_vectors(owner_a, 5)
        assert vectorstore.get_collection(owner_a).count() == 0
        assert vectorstore.get_collection(owner_b).count() == 1


class TestPerUserIsolation:
    def test_collections_are_independent(self) -> None:
        """Vectors written to A's collection never appear in B's."""
        owner_a, owner_b = _uid(), _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner_a, 1, ["alpha"], emb.embed_documents(["alpha"]))
        col_b = vectorstore.get_collection(owner_b)
        assert col_b.count() == 0

    def test_same_doc_id_isolated_across_owners(self) -> None:
        """Identical (document_id) in two owners stays separated by collection."""
        owner_a, owner_b = _uid(), _uid()
        emb = get_embeddings()
        vectorstore.upsert_chunks(owner_a, 1, ["a-data"], emb.embed_documents(["a-data"]))
        vectorstore.upsert_chunks(owner_b, 1, ["b-data"], emb.embed_documents(["b-data"]))
        a_docs = vectorstore.get_collection(owner_a).get(where={"document_id": "1"})["documents"]
        b_docs = vectorstore.get_collection(owner_b).get(where={"document_id": "1"})["documents"]
        assert a_docs == ["a-data"]
        assert b_docs == ["b-data"]


# ===========================================================================
# pipeline.extract_text
# ===========================================================================


class TestExtractText:
    def test_txt_returns_content(self) -> None:
        path = _write_temp("plain text body", ".txt")
        assert pipeline.extract_text(path, "text/plain") == "plain text body"

    def test_md_returns_content(self) -> None:
        path = _write_temp("# Title\n\nbody here", ".md")
        assert pipeline.extract_text(path, "text/markdown") == "# Title\n\nbody here"

    def test_txt_unicode_round_trips(self) -> None:
        content = "héllo wörld ünïcode 日本語 — em dash"
        path = _write_temp(content, ".txt")
        assert pipeline.extract_text(path, "text/plain") == content

    def test_md_unicode_round_trips(self) -> None:
        content = "# Café ☕\n\nNaïve façade 漢字"
        path = _write_temp(content, ".md")
        assert pipeline.extract_text(path, "text/markdown") == content

    def test_pdf_returns_text(self) -> None:
        path = _write_temp(_PDF_WITH_TEXT, ".pdf")
        assert pipeline.extract_text(path, "application/pdf") == "Hello World"

    def test_pdf_dispatched_by_content_type(self) -> None:
        """A '.bin' file with a pdf content_type is still parsed as PDF."""
        path = _write_temp(_PDF_WITH_TEXT, ".bin")
        assert pipeline.extract_text(path, "application/pdf") == "Hello World"

    def test_pdf_dispatched_by_extension_when_ct_blank(self) -> None:
        """Empty content_type falls back to the .pdf extension for parsing."""
        path = _write_temp(_PDF_WITH_TEXT, ".pdf")
        assert pipeline.extract_text(path, "") == "Hello World"

    def test_empty_content_type_reads_as_text(self) -> None:
        """No content_type + non-pdf extension → read as a UTF-8 text file."""
        path = _write_temp("fallback body", ".txt")
        assert pipeline.extract_text(path, "") == "fallback body"

    def test_none_content_type_reads_as_text(self) -> None:
        """A None content_type is coerced safely and read as text."""
        path = _write_temp("none ct body", ".txt")
        assert pipeline.extract_text(path, None) == "none ct body"  # type: ignore[arg-type]

    def test_empty_text_file_returns_empty_string(self) -> None:
        """extract_text itself does not guard emptiness — returns ''."""
        path = _write_temp("", ".txt")
        assert pipeline.extract_text(path, "text/plain") == ""

    def test_whitespace_only_returned_verbatim(self) -> None:
        path = _write_temp("   \n\t ", ".txt")
        assert pipeline.extract_text(path, "text/plain") == "   \n\t "


# ===========================================================================
# pipeline.run_ingestion
# ===========================================================================


class TestRunIngestion:
    def test_txt_returns_chunk_count_and_writes_vectors(self) -> None:
        job = _make_job("Some readable plain text content for ingestion.", ".txt", "text/plain")
        count = pipeline.run_ingestion(job)
        assert count == 1
        col = vectorstore.get_collection(job.owner_id)
        assert col.count() == count

    def test_md_ingestion_succeeds(self) -> None:
        job = _make_job("# MD Heading\n\nMarkdown body to embed.", ".md", "text/markdown")
        count = pipeline.run_ingestion(job)
        assert count >= 1
        assert vectorstore.get_collection(job.owner_id).count() == count

    def test_pdf_ingestion_succeeds(self) -> None:
        job = _make_job(_PDF_WITH_TEXT, ".pdf", "application/pdf")
        count = pipeline.run_ingestion(job)
        assert count == 1
        col = vectorstore.get_collection(job.owner_id)
        assert col.get()["documents"] == ["Hello World"]

    def test_vectors_carry_document_id_metadata(self) -> None:
        job = _make_job("Metadata check text.", ".txt", "text/plain")
        pipeline.run_ingestion(job)
        metas = vectorstore.get_collection(job.owner_id).get()["metadatas"]
        assert all(m["document_id"] == str(job.source_document_id) for m in metas)

    def test_ids_use_document_id_prefix(self) -> None:
        job = _make_job("Id prefix text.", ".txt", "text/plain")
        pipeline.run_ingestion(job)
        ids = vectorstore.get_collection(job.owner_id).get()["ids"]
        assert all(i.startswith(f"{job.source_document_id}:") for i in ids)

    def test_empty_document_raises_valueerror(self) -> None:
        job = _make_job("", ".txt", "text/plain")
        with pytest.raises(ValueError, match="No extractable text"):
            pipeline.run_ingestion(job)

    def test_whitespace_only_document_raises(self) -> None:
        job = _make_job("   \n\t  \r\n ", ".txt", "text/plain")
        with pytest.raises(ValueError, match="No extractable text"):
            pipeline.run_ingestion(job)

    def test_empty_document_writes_no_vectors(self) -> None:
        job = _make_job("", ".txt", "text/plain")
        with pytest.raises(ValueError):
            pipeline.run_ingestion(job)
        assert vectorstore.get_collection(job.owner_id).count() == 0

    def test_long_text_splits_per_chunk_params(self) -> None:
        """~3000-char body → 4 chunks under chunk_size=1000 / overlap=150."""
        assert settings.CHUNK_SIZE == 1000
        assert settings.CHUNK_OVERLAP == 150
        body = ("word " * 600).strip()  # 2999 chars
        job = _make_job(body, ".txt", "text/plain")
        count = pipeline.run_ingestion(job)
        assert count == 4
        assert vectorstore.get_collection(job.owner_id).count() == 4

    def test_short_text_is_single_chunk(self) -> None:
        job = _make_job("short body under one chunk", ".txt", "text/plain")
        assert pipeline.run_ingestion(job) == 1

    def test_each_chunk_within_chunk_size(self) -> None:
        """No produced chunk exceeds the configured chunk_size."""
        body = ("token " * 800).strip()
        job = _make_job(body, ".txt", "text/plain")
        pipeline.run_ingestion(job)
        docs = vectorstore.get_collection(job.owner_id).get()["documents"]
        assert all(len(d) <= settings.CHUNK_SIZE for d in docs)

    def test_unicode_document_ingests(self) -> None:
        job = _make_job("Café ünïcode 日本語 content body.", ".md", "text/markdown")
        count = pipeline.run_ingestion(job)
        assert count >= 1

    def test_ingestion_isolated_per_owner(self) -> None:
        """Two jobs with distinct owners write to distinct collections."""
        job_a = _make_job("Owner A document text.", ".txt", "text/plain")
        job_b = _make_job("Owner B document text.", ".txt", "text/plain")
        pipeline.run_ingestion(job_a)
        pipeline.run_ingestion(job_b)
        col_a = vectorstore.get_collection(job_a.owner_id)
        col_b = vectorstore.get_collection(job_b.owner_id)
        assert col_a.get()["documents"] == ["Owner A document text."]
        assert col_b.get()["documents"] == ["Owner B document text."]

    def test_reingest_same_job_is_idempotent(self) -> None:
        """Running the same job twice overwrites; count stays stable."""
        job = _make_job("Idempotent ingestion body.", ".txt", "text/plain")
        first = pipeline.run_ingestion(job)
        second = pipeline.run_ingestion(job)
        assert first == second
        assert vectorstore.get_collection(job.owner_id).count() == first

    def test_query_after_ingestion_finds_chunk(self) -> None:
        """End-to-end: ingest then retrieve the same text via query()."""
        job = _make_job("Retrievable unique sentence about turtles.", ".txt", "text/plain")
        pipeline.run_ingestion(job)
        emb = get_embeddings()
        res = vectorstore.query(
            job.owner_id, emb.embed_query("Retrievable unique sentence about turtles."), 4
        )
        assert "Retrievable unique sentence about turtles." in res["documents"][0]
