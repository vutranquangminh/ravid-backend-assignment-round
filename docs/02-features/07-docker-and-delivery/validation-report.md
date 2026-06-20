# Validation Report — 07 Docker & delivery

> Branch `feature/07-docker-and-delivery-compose-ci` (base `main`). Env: `.venv` + `rag` extra. **Docker daemon NOT available in the authoring environment** → containers validated statically; `docker compose up` is the reviewer's step.

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `manage.py check` (test settings) | system check | ✅ `0 issues` | re-run independently |
| `manage.py check` (production settings) | prod import-clean | ✅ `0 issues` | re-run with env vars |
| `python -m pytest -q` | full suite | ✅ `620 passed` | 48 new delivery/vectorstore tests + 572 prior |
| `ruff check apps/ tests/ config/` | lint | ✅ `All checks passed!` | — |
| `docker compose -f compose.yaml config` | compose syntax | ✅ valid (with `.env` from `.env.example`) | re-run independently |
| `docker compose -f compose.ci.yaml config` | CI compose syntax | ✅ valid | — |
| `pre-commit run --all-files` | hooks | ✅ all pass | — |

## Brief compliance (Part 4)

| Requirement | Implemented |
|-------------|-------------|
| Docker + Compose: web, database, Redis, Celery, dashboard | ✅ web, db (postgres), redis, celery, **grafana** dashboard (+ loki, alloy, chroma) |
| Docker commands in README | ✅ `docker compose up --build` + URLs |
| API documentation (Postman/OpenAPI/etc.) | ✅ live drf-spectacular `/api/schema/` + Swagger `/api/docs/` + Postman collection + hand-written `api_contract.yaml` |
| README setup/run instructions | ✅ full reviewer guide |

## Failures Or Gaps

- **No live container run here** — the Docker daemon isn't running in the authoring env, so `docker compose up`, image build, and end-to-end health were NOT executed. Mitigations: `docker compose config` validates both files; structure tests assert the topology; production settings import cleanly; README documents exact run steps. **Reviewer must run `docker compose up --build` to confirm the live stack.**
- **Real OpenRouter + embeddings** run only inside the container (needs a key in `.env`); CI and tests stay stubbed/offline.
- `chromadb/chroma:1.5.9` image pinned to match the client; heartbeat path may differ across chroma versions — documented.

## Mistake check

`No active mistake repeated.` (M-004: README + API docs + delivery artifacts shipped, not deferred; M-008: no secrets committed — `.env` gitignored, `.env.example` placeholders only; M-009: chroma image pinned to the installed client version, not guessed.)
