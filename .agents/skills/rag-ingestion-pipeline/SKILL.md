---
name: rag-ingestion-pipeline
description: Build the document ingestion and background processing pipeline for the RAVID assessment. Use when working on upload validation, document metadata, Celery task queuing, LangChain load/split/embed, per-user Chroma upsert, ingestion task state, failure propagation from background jobs to the task-status API, and secret/document-text safety.
---

# RAG Ingestion Pipeline

## Purpose

Use this skill for the async document ingestion workflow (`apps/documents` + `apps/rag` ingestion side), not for generic Django setup and not for chat retrieval. This replaces the CSV pipeline: the operation is `load -> split -> embed -> Chroma upsert` per user, run as a Celery `IngestionJob`.

## Read Before Work

1. `.agents/MISTAKE.md`
2. `.agents/guidelines/llm-provider-guidelines.md`
3. `.agents/references/assessment-decisions.md`
4. The active `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}`
5. `docs/02-features/<NN-name>/test_matrix.md`

## Scope

- uploaded file handling and storage
- document metadata persistence (owner FK, filename, content type, size, status)
- upload validation before dispatch
- Celery task queuing (`IngestionJob`)
- LangChain loaders (PDF/TXT/MD)
- `RecursiveCharacterTextSplitter` chunking
- local HuggingFace embedding generation
- per-user Chroma collection upsert
- ingestion task-status state machine
- failure propagation to logs and to the status API

## Locked Pipeline Values

- Allowed uploads: `.pdf .txt .md` only, max 10 MB. Reject others with `400 {"error": "..."}` at the API layer before queuing.
- Chunking: `RecursiveCharacterTextSplitter` with `chunk_size=1000`, `chunk_overlap=150`.
- Embeddings: local HuggingFace `all-MiniLM-L6-v2` (384 dims) via `langchain-huggingface`. Free, offline, no key. OpenRouter has no embeddings, so do not call a remote embedding API.
- Vector isolation: one Chroma collection per user named `user_{user_id}`. Upsert every chunk into the owner's collection only.

## Task-Status State Machine

The status endpoint returns one of `PROCESSING | SUCCESS | FAILURE` plus details. Keep an internal-vs-public mapping: internal Celery/job states map to these three public values. The DB row is the source of truth for status, not the Celery result backend alone. Cross-user task lookups return `404` (not `403`).

- `PROCESSING`: queued or running (loading, splitting, embedding, upserting)
- `SUCCESS`: all chunks embedded and upserted into `user_{user_id}`
- `FAILURE`: parse/embed/upsert error; include a safe error message (no raw document text)

## Rules

- Validate the upload (type, size, presence of `file`) before dispatching a Celery task.
- Keep heavy ingestion work out of the request-response path; the upload view returns `202 {message, document_id, task_id}` immediately.
- Make task failures visible in BOTH structured logs and the task-status output (M-006: do not swallow embedding/parse failures).
- Scope every upsert to the authenticated owner's collection `user_{user_id}`; never write a user's chunks into another collection (M-005: cross-user vector/chunk leakage).
- Never log raw document text, embedding keys, or OpenRouter keys (M-008). Log document_id, task_id, user_id, chunk count, status, and timings instead.
- Document the chunk/embedding/collection schema and any status fields beyond the PDF examples before implementing them (M-003: no silent ambiguity).

## Required Checks

- Tests for successful ingestion of each allowed type (PDF, TXT, MD)
- Tests for rejected uploads (wrong extension, over 10 MB, missing file) -> 400
- Tests for missing/invalid task IDs and cross-user task lookups -> 404
- Test that a parse/embed failure surfaces as `FAILURE` in the status API and is logged
- Test that chunks land in `user_{user_id}` and not in any other user's collection
- Validation that success and failure status payloads match the OpenSpec change

## Output

When this skill is used, the result should include:

- updated ingestion pipeline code (validation, Celery `IngestionJob`, load/split/embed/upsert)
- updated task-status contract in the OpenSpec change if it changed
- updated tests
- updated `docs/02-features/<NN-name>/test_matrix.md` if coverage changed
- validation evidence
