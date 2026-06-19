# Validation Report — 04 Ingestion pipeline

> Branch `feature/04-ingestion-pipeline-chunk-embed-chroma` (base `main`). Env: `.venv` with the `rag` extra (chromadb, langchain, langchain-huggingface, sentence-transformers, pypdf). Tests offline: stub embeddings + temp Chroma.

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `pip install -e '.[rag]'` | Install ML/vector stack | ✅ chromadb 1.5.9, langchain 1.3.x, sentence-transformers, torch | — |
| `makemigrations rag` | IngestionJob migration | ✅ `0001_initial` | checked in |
| `manage.py check` | Django system check | ✅ `0 issues` | re-run independently |
| `python -m pytest -q` | Full suite | ✅ `151 passed` | 36 new ingestion + 115 prior |
| `ruff check apps/ tests/ config/` | Lint | ✅ `All checks passed!` | fixed F841 + SIM105 found during review |
| `pre-commit run --all-files` | Hooks | ✅ all pass | — |

## Brief compliance (Part 2 — ingestion + status)

| Aspect | Brief | Implemented |
|--------|-------|-------------|
| Background pipeline | extract → chunk (RecursiveCharacterTextSplitter) → embed → vector store, per-user namespace | ✅ chunk 1000/150, per-user `user_<id>` Chroma |
| `GET /api/documents/status/` | PROCESSING / SUCCESS / FAILURE bodies | ✅ exact, incl. success message |
| Celery worker | async ingestion | ✅ `ingest_document` task, eager in tests |

## Failures Or Gaps

- **Real embeddings not exercised in tests** — stubbed (deterministic 32-dim) to stay offline/fast; real `all-MiniLM-L6-v2` downloads ~80 MB on first production run (documented in README/Docker slice 07).
- **Chroma runs as a local persistent client** here; slice 07 adds a `chroma` compose service + `CHROMA_PERSIST_DIR` volume.
- `/api/chat/query/` retrieval over these vectors is slice 05.

## Mistake check

`No active mistake repeated.` (M-005: collections + jobs strictly `owner`-scoped, cross-user → 404; M-006: failures set FAILURE + error_message AND logged, never swallowed; M-008: only ids/metadata logged — never document text or keys; M-009: chromadb/langchain wired against the actually-installed versions, verified by running, not memory.)

> Reviewer note: two lint issues (unused `token_b`, `try/except/pass`) were caught during this slice's review and fixed before commit — `ruff check` is clean.
