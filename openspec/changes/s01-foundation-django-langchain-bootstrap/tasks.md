# Tasks — s01 Foundation

## 1. Project skeleton
- [ ] 1.1 Add `manage.py` and `config/` package (`__init__.py`, `wsgi.py`, `asgi.py`, `urls.py`).
- [ ] 1.2 Add split settings `config/settings/{__init__,base,local,test}.py`; default `DJANGO_SETTINGS_MODULE=config.settings.local`.
- [ ] 1.3 Add `config/celery.py` and load the Celery app in `config/__init__.py`.

## 2. Dependencies
- [ ] 2.1 Promote `pyproject.toml` to `[build-system]` + `[project]` with runtime deps (django, djangorestframework, djangorestframework-simplejwt, celery[redis], psycopg[binary], langchain, langchain-text-splitters, langchain-huggingface, chromadb, pypdf, python-json-logger).
- [ ] 2.2 Add a `dev` optional-dependencies extra (pytest, pytest-django, pytest-cov, ruff) and `[tool.pytest.ini_options]`.
- [ ] 2.3 Preserve slice-00 `[tool.ruff]` / `[tool.commitizen]` config.

## 3. Common infrastructure (`apps/common`)
- [ ] 3.1 `env.py` helpers: `env`, `env_bool`, `env_int`, `env_list`.
- [ ] 3.2 Structured JSON logging config (`python-json-logger`) on root + celery loggers.
- [ ] 3.3 `RequestIdMiddleware` + `RequestLoggingMiddleware` (request_id, method, path, status, duration_ms).

## 4. Apps and health endpoint
- [ ] 4.1 Create `apps/{accounts,documents,rag,common}` packages with explicit `AppConfig`s.
- [ ] 4.2 Implement `GET /api/health/` (AllowAny) returning `{"status":"ok"}` 200.
- [ ] 4.3 Wire root `config/urls.py`; reserve (commented) includes for later slices.

## 5. Offline test posture
- [ ] 5.1 `config/settings/test.py`: `CELERY_TASK_ALWAYS_EAGER=True`, temp Chroma persist dir, fast password hasher, stub seams for embedding + OpenRouter.
- [ ] 5.2 Ensure the suite imports no ML libraries (torch/chromadb) on the foundation path.

## 6. Tests
- [ ] 6.1 Smoke: Django system check clean; `/api/health/` returns 200 `{"status":"ok"}`.
- [ ] 6.2 Unit: env helpers parse bool/int/list correctly.
- [ ] 6.3 Regression: `/api/documents/upload/`, `/api/documents/status/`, `/api/chat/query/`, `/api/register/`, `/api/login/` are ABSENT (404/resolver error) — they arrive in later slices.

## 7. Validate & deliver
- [ ] 7.1 Create a venv, install `.[dev]` (core), run `python manage.py check` and `pytest` green.
- [ ] 7.2 `pre-commit run --all-files` clean.
- [ ] 7.3 Author `docs/02-features/01-foundation/{test_matrix,validation-report,pull_request}.md` and record literal command output.
- [ ] 7.4 Open PR into `main` (stacked on slice 00 until merged); `openspec archive` after merge.
