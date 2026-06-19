"""RAG ingestion pipeline: extract → chunk → embed → upsert (slice 04).

``extract_text`` supports PDF (via pypdf.PdfReader), TXT, and MD (UTF-8 read).
``run_ingestion`` orchestrates the full pipeline for a given ``IngestionJob``
and returns the number of chunks written.  It is intentionally pure-ish
(no DB writes) so it is easy to unit-test in isolation.

Tech constraints (from the spec):
  - Text splitting: ``langchain_text_splitters.RecursiveCharacterTextSplitter``
    with ``chunk_size=settings.CHUNK_SIZE``, ``chunk_overlap=settings.CHUNK_OVERLAP``.
  - PDF extraction: ``pypdf.PdfReader`` directly (NOT PyPDFLoader).
  - Embeddings: via ``apps.rag.embeddings.get_embeddings()`` (stubbed in tests).
  - Vector store: ``apps.rag.vectorstore.upsert_chunks()``.
"""

from __future__ import annotations

from django.conf import settings

# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(file_path: str, content_type: str) -> str:
    """Extract the full plain text from a stored document file.

    Args:
        file_path:    Absolute filesystem path to the saved file.
        content_type: MIME type reported at upload (used to choose the parser).

    Returns:
        The concatenated text content of the document.

    Raises:
        ValueError: If the extracted text is empty or whitespace-only.
    """
    ct = (content_type or "").lower()

    if "pdf" in ct or file_path.lower().endswith(".pdf"):
        return _extract_pdf(file_path)

    # TXT and MD — read as UTF-8.
    return _extract_text_file(file_path)


def _extract_pdf(file_path: str) -> str:
    """Use pypdf.PdfReader to concatenate text from all pages."""
    import pypdf  # noqa: PLC0415 — deferred import; kept out of global scope

    reader = pypdf.PdfReader(file_path)
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n".join(parts)


def _extract_text_file(file_path: str) -> str:
    """Read a plain-text file (TXT / MD) as UTF-8."""
    with open(file_path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def run_ingestion(job: object) -> int:
    """Run the full ingestion pipeline for *job* and return the chunk count.

    Pipeline steps:
      1. Extract text from ``job.source_document.file.path``.
      2. Validate that the text is not empty.
      3. Split into chunks via ``RecursiveCharacterTextSplitter``.
      4. Embed all chunks via ``get_embeddings().embed_documents()``.
      5. Upsert into the owner's Chroma collection.

    Args:
        job: An ``IngestionJob`` instance (must have ``owner_id``,
             ``source_document``, and ``source_document.file.path``).

    Returns:
        The number of chunks written to Chroma.

    Raises:
        ValueError: If the document yields no extractable text.
        Any exception from pypdf / langchain / chromadb propagates so the
        caller (``ingest_document`` task) can mark the job FAILURE.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: PLC0415

    from apps.rag.embeddings import get_embeddings  # noqa: PLC0415
    from apps.rag.vectorstore import upsert_chunks  # noqa: PLC0415

    doc = job.source_document
    file_path: str = doc.file.path
    content_type: str = doc.content_type or ""

    # Step 1 — extract
    raw_text = extract_text(file_path, content_type)

    # Step 2 — guard: reject empty documents
    if not raw_text or not raw_text.strip():
        raise ValueError("No extractable text in document.")

    # Step 3 — chunk
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    chunks: list[str] = splitter.split_text(raw_text)
    if not chunks:
        raise ValueError("No extractable text in document.")

    # Step 4 — embed
    embeddings_obj = get_embeddings()
    vectors: list[list[float]] = embeddings_obj.embed_documents(chunks)

    # Step 5 — upsert
    upsert_chunks(
        owner_id=job.owner_id,
        document_id=job.source_document_id,
        texts=chunks,
        embeddings=vectors,
    )

    return len(chunks)
