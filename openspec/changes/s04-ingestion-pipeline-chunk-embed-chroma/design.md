# Design — s04 Ingestion pipeline

## Context

Slice 03 left `ingest_document` as a placeholder and returns a Celery `task_id`. This slice implements the real pipeline and the status endpoint, introducing Chroma + embeddings (the `rag` extra). Tests must stay offline and fast, so embeddings are stubbed and Chroma uses a temp dir.

## Goals / Non-Goals

**Goals:**
- Real async ingestion: extract → chunk (1000/150) → embed → per-user Chroma upsert.
- `GET /api/documents/status/?task_id=` matching the brief's PROCESSING/SUCCESS/FAILURE bodies.
- Per-user isolation of jobs (status 404 cross-user) and vectors (collection per owner).
- Failures captured in logs AND the job row; DB row is source of truth.
- Offline, deterministic tests (no model download, no network).

**Non-Goals:**
- No chat/retrieval (slice 05). No Docker/Chroma-server (slice 07; this slice uses a local persistent Chroma client).

## Decisions

- **task_id ↔ job:** the view creates `Document`, then `result = ingest_document.delay(doc.id)`, then `IngestionJob.objects.create(owner, source_document=doc, celery_task_id=result.id, status="PENDING")` — except eager mode runs the task inline first, so instead: create the `IngestionJob` with `status=PENDING` FIRST (no id), call `.delay(job.id)`, then set `celery_task_id=result.id` via a `.filter(pk=).update(...)`. The task receives `job.id`, loads the job, and drives its status. Status endpoint queries by `celery_task_id`. This avoids the eager chicken-and-egg and the real-mode race.
- **Status state machine (in the task):** `PENDING` → `STARTED` (on task entry) → `SUCCESS` (+`chunk_count`) or `FAILURE` (+`error_message`). Use `IngestionJob.objects.filter(pk=).update(...)` for atomic transitions.
- **Public status mapping (status endpoint):** internal `PENDING`/`STARTED` → `"PROCESSING"`; `SUCCESS` → `"SUCCESS"` + message "Document successfully parsed, embedded, and indexed in vector storage."; `FAILURE` → `"FAILURE"` + `error`.
- **Text extraction (robust, minimal langchain surface):** PDF via `pypdf.PdfReader` (concatenate page text); TXT/MD read as UTF-8. Then chunk with **`langchain_text_splitters.RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)`** (LangChain required by the brief, used here). Avoid `PyPDFLoader`/`langchain_chroma` to dodge langchain-1.x API churn and an extra dependency.
- **Embeddings factory:** `apps/rag/embeddings.py::get_embeddings()` returns `langchain_huggingface.HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)` by default. `config.settings.test` sets `RAVID_EMBEDDINGS_STUB=True` → a deterministic fake with `embed_documents(list[str])`/`embed_query(str)` returning fixed-dim hash-based vectors (no model download, no network).
- **Vector store: chromadb client directly** (NOT langchain_chroma). `chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)`; `get_or_create_collection(f"user_{owner_id}")`; `collection.upsert(ids, embeddings, documents, metadatas)` with `ids="<document_id>:<chunk_index>"`, `metadatas={document_id, chunk_index}` (idempotent re-ingest). Slice 05's retriever uses the SAME client + collection naming (`collection.query(query_embeddings=..., where={"document_id":...} optional)`).
- **Isolation:** every Chroma read/write keyed to `user_<owner_id>`; status queries filter `owner=request.user`; cross-user/unknown → 404. (M-005.)
- **Delete integration:** `delete_document` also deletes that document's vectors from the user's collection (by `document_id` metadata filter). Wired here now that Chroma exists.
- **Failure handling:** wrap the pipeline in try/except; on any error set `FAILURE` + concise `error_message`, log `operation=ingest status=failure document_id=... error=...`, and DO NOT swallow (M-006). Never log document text or secrets (M-008).

## Risks / Trade-offs

- **Heavy deps / model download:** real `all-MiniLM-L6-v2` would download ~80 MB on first use. Mitigation: stub embeddings in tests; the README documents a first-run warm-up for real use.
- **Chroma persistence in tests:** temp dir per test session; ensure cleanup and unique collections to avoid cross-test bleed.
- **Eager-mode semantics:** in tests the task runs synchronously, so status is terminal (SUCCESS/FAILURE) right after upload; a dedicated test simulates the PROCESSING (PENDING/STARTED) mapping by constructing a job row directly.
