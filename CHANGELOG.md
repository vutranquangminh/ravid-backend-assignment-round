# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); commits follow Conventional Commits.

## [1.0.0] — 2026-06-20

Initial delivery of the RAVID RAG document-chatbot backend (assessment Parts 1–4 + bonus).

### Added
- **Foundation** — spec-driven workflow (OpenSpec + `.agents/`), architecture docs, `api_contract.yaml`, pre-commit (ruff + commitizen).
- **Bootstrap** — Django 5 + DRF + Celery skeleton, split settings, structured JSON logging + request-id middleware, `GET /api/health/`.
- **Part 1 — Auth** — `POST /api/register/`, `POST /api/login/` (JWT), `GET /api/auth/me/`, global `IsAuthenticated`, `{error}` envelope.
- **Part 2 — Documents** — `POST /api/documents/upload/` (PDF/TXT/MD, 202 + task_id), async Celery ingestion (chunk → embed → per-user Chroma collection), `GET /api/documents/status/`, `GET /api/documents/` (owner-scoped list), and `DELETE /api/documents/<id>/`.
- **Part 3 — RAG chat** — `POST /api/chat/query/` (owner-scoped retrieval → OpenRouter → `{answer, tokens_consumed}`), per-user credit consumption, no-context guard.
- **Part 4 — Delivery** — Docker Compose (web, db, redis, celery, chroma, grafana/loki/alloy), production settings, live API docs (`/api/schema/` OpenAPI + `/api/docs/` Swagger UI), Postman collection, CI pipeline, README.
- **Bonus** — chat continuation via `chat_id` (owner-scoped) and SSE streaming (`POST /api/chat/stream/`).
- **Quality** — 754 offline tests at 100% coverage (CI gate `--cov-fail-under=95`); sharded CI (unit/integration/smoke) + container validation; `main` branch protection with required green CI.

### Security
- Per-user data isolation across documents, ingestion jobs, vectors, and chat (cross-user access → 404; invalid JWT → 401).
- No secrets or document text logged; `.env` gitignored, `.env.example` provided.
