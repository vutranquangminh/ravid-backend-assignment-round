# Test Matrix — 01 Foundation (Django + LangChain bootstrap)

> Spec: `openspec/changes/s01-foundation-django-langchain-bootstrap/`. Settings: `config.settings.test` (offline, key-free).

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Happy | Django system check is clean | Smoke | `0 issues` | `python manage.py check` |
| Happy | `GET /api/health/` returns liveness | Smoke | `200 {"status":"ok"}` | `tests/smoke/test_foundation.py` |
| Auth | Health is public (no token) | Smoke | `200` without Authorization header | `tests/smoke/test_foundation.py` |
| Validation | env helpers parse bool/int/list/default | Unit | correct typed values | `tests/unit/test_env.py` |
| Observability | each request logged with `request_id`, method, path, status, `duration_ms` | Manual/Design | JSON log line per request; `X-Request-ID` echoed | `apps/common/middleware.py`; `config/settings/base.py` LOGGING |
| Async | Celery configured; eager in tests | Smoke | `CELERY_TASK_ALWAYS_EAGER=True`; no broker needed | `config/settings/test.py`; `config/celery.py` |
| Docker | (deferred to slice 07) | — | n/a this slice | — |
| Regression | future endpoints not yet routable | Smoke | `/api/{documents/upload,documents/status,chat/query,register,login}/` → 404 | `tests/smoke/test_endpoints_absent.py` |
| Hygiene | lint/format/commit hooks pass | CI/Local | all hooks Passed | `pre-commit run --all-files` |

**Coverage notes:** Auth/Upload/Ingestion/Chat behavioral areas are intentionally empty this slice — they are owned by slices 02–05. The foundation suite must not import ML libs (torch/chromadb); enforced by keeping those in the `rag` extra.
