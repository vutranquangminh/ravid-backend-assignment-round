# Tasks — s04 Ingestion pipeline

## 1. Settings
- [ ] 1.1 `base.py`: `CHROMA_PERSIST_DIR` (env, default `<BASE_DIR>/chroma_data`), `EMBEDDING_MODEL` (default `sentence-transformers/all-MiniLM-L6-v2`), `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=150`, `RETRIEVAL_TOP_K=4`.
- [ ] 1.2 `test.py`: `RAVID_EMBEDDINGS_STUB=True`, `CHROMA_PERSIST_DIR=tempfile.mkdtemp(...)`.

## 2. IngestionJob model
- [ ] 2.1 `apps/rag/models.py`: `IngestionJob` (owner FK, source_document FK CASCADE, status PENDING/STARTED/SUCCESS/FAILURE, celery_task_id unique+indexed, chunk_count default 0, error_message blank, created_at/updated_at).
- [ ] 2.2 `makemigrations rag`; check in.

## 3. Embeddings + vector store + pipeline
- [ ] 3.1 `apps/rag/embeddings.py`: `get_embeddings()` (HuggingFace default; deterministic stub when `RAVID_EMBEDDINGS_STUB`).
- [ ] 3.2 `apps/rag/vectorstore.py`: chromadb PersistentClient helpers — `get_collection(owner_id)`, `upsert_chunks(owner_id, document_id, texts, embeddings)`, `delete_document_vectors(owner_id, document_id)`, `query(owner_id, query_embedding, k)`.
- [ ] 3.3 `apps/rag/pipeline.py`: `extract_text(path, content_type)` (pypdf for PDF, UTF-8 read for TXT/MD) → `split` (RecursiveCharacterTextSplitter 1000/150) → embed → upsert; returns `chunk_count`. Pure/unit-testable.

## 4. Task state machine
- [ ] 4.1 `apps/rag/tasks.py`: real `ingest_document(self, job_id)` — load job, set STARTED, run pipeline, set SUCCESS + chunk_count OR FAILURE + error_message; log `operation=ingest` (no secrets/text). Atomic `.update()` transitions.

## 5. Upload integration + status endpoint
- [ ] 5.1 Update `apps/documents` upload: create `IngestionJob` (PENDING), `ingest_document.delay(job.id)`, set `celery_task_id=result.id`; response unchanged (202 + document_id + task_id).
- [ ] 5.2 Update `delete_document` to also call `delete_document_vectors`.
- [ ] 5.3 `apps/rag/views.py` `StatusView` (GET `/api/documents/status/?task_id=`, JWT): owner-scoped lookup by celery_task_id; map PENDING/STARTED→PROCESSING, SUCCESS (+message), FAILURE (+error); unknown/cross-user → 404.
- [ ] 5.4 `apps/rag/urls.py` + include in `config/urls.py`.

## 6. Tests (offline: stub embeddings, temp Chroma)
- [ ] 6.1 Pipeline unit: extract/split/chunk_count for PDF/TXT/MD; upsert writes to `user_<id>` collection.
- [ ] 6.2 Integration: upload → status SUCCESS + message; status response shape per brief; chunk_count > 0.
- [ ] 6.3 Failure: corrupt/empty doc → job FAILURE + error_message; status returns FAILURE + error; failure logged.
- [ ] 6.4 Isolation: user B cannot read user A's job status (404); A's vectors in `user_A` collection only; delete removes vectors.
- [ ] 6.5 Status mapping: a constructed PENDING/STARTED job → PROCESSING.
- [ ] 6.6 Regression: `/api/chat/query/` still ABSENT (404); `/api/documents/status/` now present.

## 7. Validate & deliver
- [ ] 7.1 `pip install -e '.[rag]'`; `manage.py check`; `pytest` green; `pre-commit` clean.
- [ ] 7.2 `docs/02-features/04-ingestion-pipeline/{test_matrix,validation-report,pull_request}.md`.
- [ ] 7.3 PR into `main` (base main, no branch deletion); `openspec archive s04` after merge.
