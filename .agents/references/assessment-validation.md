# Assessment Validation

This file records the practical interpretation of the RAVID brief (`docs/00-anchor/srs.md`) for
implementation work, plus the **validation command catalogue** — the commands every slice runs to
prove it satisfies the locked decisions in `.agents/references/assessment-decisions.md`.

## Validation Summary

- The assessment is implementable without blocker.
- The major workstreams are:
  - API surface (register/login, document upload, ingestion status, chat query)
  - authentication (JWT-protected routes)
  - RAG ingestion (LangChain load → split → embed → Chroma upsert, async in Celery)
  - RAG retrieval + chat (top_k retrieval → OpenRouter LLM → grounded answer + tokens)
  - per-user vector isolation + credit accounting
  - structured observability (Django + Celery JSON logs → Alloy → Loki → Grafana)
  - Dockerized delivery
- The assessment is time-boxed, so defaults are **locked early** (see assessment-decisions.md) to
  avoid repeated redesign.

## Validated Requirement Areas

### Part 1: API Surface
- `POST /api/documents/upload/` — multipart `file`; returns `202 {message, document_id, task_id}`.
- `GET /api/documents/status/?task_id=<id>` — returns `{task_id, status, ...}`.
- `POST /api/chat/query/` — JSON `{query}`; returns `200 {answer, tokens_consumed}`.

### Part 2: Authentication
- `POST /api/register/` — JSON `{email, password}`.
- `POST /api/login/` — JSON `{email, password}`; returns `{message, token}`.
- JWT required on `documents/*` and `chat/*`.

### Part 3: RAG Pipeline
- LangChain loaders for `.pdf` / `.txt` / `.md`.
- `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)` [D-011].
- Local HuggingFace `all-MiniLM-L6-v2` (384 dims) embeddings [D-010].
- Per-user Chroma collection `user_{user_id}` [D-013]; `top_k=4`, cosine [D-012].

### Part 4: Structured Observability
- Django JSON logs.
- Celery JSON logs with task metadata.
- log shipping to Loki via Grafana Alloy.
- Grafana datasource + dashboard provisioning.

### Part 5: Docker And Finalization
- Docker + Docker Compose for `web`, `db`, `redis`, `celery`, `chroma`, `alloy`/`loki`/`grafana`.
- README run instructions.
- API documentation.

---

## Validation Command Catalogue

Run from the repo root with the stack up (`docker compose up -d`) unless noted. External calls
(OpenRouter, model downloads) are **stubbed** in CI/tests; live smokes are run manually before
submission. Each command notes which decision(s) it proves.

### V-01 — Unit & integration tests (pytest)
```bash
docker compose exec web pytest -q
```
Runs the full suite. Proves serializers, ownership rules, status mapping, retrieval scoping.

### V-02 — Coverage gate
```bash
docker compose exec web pytest --cov=apps --cov-report=term-missing --cov-fail-under=80
```
Fails the slice if coverage drops below the threshold. (Threshold set in the foundation slice.)

### V-03 — API smoke: register → login
```bash
curl -sf -X POST localhost:8000/api/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"S3cret-pass"}'        # expect 201 {message,user_id}
curl -sf -X POST localhost:8000/api/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"S3cret-pass"}'        # expect 200 {message,token}
```
Proves D-017 register/login contract and D-022 error envelope (try a bad password → 401).

### V-04 — JWT smoke: protected route rejects/accepts
```bash
# no token -> 401 (D-021)
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/chat/query/   # expect 401
# with token -> not 401
TOKEN=...   # from V-03
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"hi"}' localhost:8000/api/chat/query/                       # expect 200/400, not 401
```
Proves D-021 (401) and that JWT is enforced.

### V-05 — Upload validation smoke (accept/reject)
```bash
# allowed type -> 202 with task_id (D-018)
curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
  -F 'file=@tests/fixtures/sample.pdf' localhost:8000/api/documents/upload/   # expect 202
# disallowed type -> 400 {error} (D-018, D-022)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -F 'file=@tests/fixtures/sample.csv' localhost:8000/api/documents/upload/   # expect 400
# oversize (>10MB) -> 400
```
Proves D-018 allowed types + size limit and the early-reject path.

### V-06 — Ingestion / Celery task-status smoke
```bash
# capture task_id from V-05 upload response, then poll:
curl -sf -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/documents/status/?task_id=$TASK_ID"   # PROCESSING -> SUCCESS over time
```
Proves D-025 async ingestion, D-019 DB-row-as-source-of-truth and PROCESSING→SUCCESS mapping.
Verify a deliberately corrupt file yields public `FAILURE` **with an error message** (D-026).

### V-07 — Retrieval + chat smoke (stubbed LLM)
```bash
docker compose exec web pytest -q tests/test_chat_query.py
```
With OpenRouter stubbed: proves `top_k=4` cosine retrieval [D-012], bounded context [D-014],
no-relevant-context guard [D-015], `tokens_consumed` read from `usage` [D-009], and credit
decrement [D-016]. Live (manual, pre-submission):
```bash
curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"What does my document say about X?"}' localhost:8000/api/chat/query/
```

### V-08 — Per-user isolation check
```bash
docker compose exec web pytest -q tests/test_isolation.py
```
Registers two users, uploads/ingests a doc for user A, then asserts:
- user B's `chat/query/` never retrieves A's chunks (separate `user_{id}` collection) [D-013].
- user B requesting A's `document_id`/`task_id` gets **404, not 403** [D-020].
Guards mistake M-005.

### V-09 — Structured-logging smoke
```bash
docker compose exec web python -c "import logging,json; logging.getLogger('ravid').info('probe')"
docker compose logs --no-color web | tail -n 5      # lines must be valid JSON
docker compose logs --no-color celery | tail -n 5   # task metadata present, no secrets/raw text
```
Proves D-029 JSON logs and D-027 (no API key / no raw document text in logs).

### V-10 — Docker Compose healthchecks
```bash
docker compose up -d
docker compose ps          # all services healthy / running
docker compose exec web python manage.py check
```
Proves the full stack (`web`, `db`, `redis`, `celery`, `chroma`, `alloy`/`loki`/`grafana`) boots
with healthchecks wired (startup order via `service_healthy`).

### V-11 — Migrations & system check
```bash
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py migrate --noinput
```
Proves models/migrations are in sync before any other smoke.

### V-12 — Foundation self-audit (agent system)
```bash
python .agents/scripts/validate_agents.py
python .agents/scripts/check_assessment_coverage.py
python .agents/scripts/check_mistake_recurrence.py
```
Proves the `.agents/` operating system is internally consistent (cross-references resolve, every
locked decision is covered, no recurring mistakes). Run on the foundation branch and before each PR.

---

## Known Ambiguities

- The register example shows only `{email, password}`; whether `confirm_password` is required is
  resolved by **D-023** (not required).
- The exact credit starting balance and behavior on insufficient credit is implied, not specified;
  resolved per-slice in the chat openspec change (see D-016).
- The OpenRouter free model slug rotates; **verify before coding** (D-008).
- Chat continuation (`chat_id`) and SSE streaming are **bonus**; mark explicitly done or not-done in
  the submission checklist.

## Chosen Defaults

See `.agents/references/assessment-decisions.md` (canonical). This file only adds the *how-to-verify*
layer on top of those decisions.
