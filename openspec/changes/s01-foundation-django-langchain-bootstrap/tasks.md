# Tasks — s01 Foundation

## 1. Project skeleton
- [x] 1.1 Add `manage.py` and `config/` package (`__init__.py`, `wsgi.py`, `asgi.py`, `urls.py`).
- [x] 1.2 Add split settings `config/settings/{__init__,base,local,test}.py`; default `DJANGO_SETTINGS_MODULE=config.settings.local`.
- [x] 1.3 Add `config/celery.py` and load the Celery app in `config/__init__.py`.

## 2. Dependencies
- [x] 2.1 Promote `pyproject.toml` to `[build-system]` + `[project]` with core runtime deps.
- [x] 2.2 Add `dev` + `rag` optional-dependencies and `[tool.pytest.ini_options]`.
- [x] 2.3 Preserve slice-00 `[tool.ruff]` / `[tool.commitizen]` config.

## 3. Common infrastructure (`apps/common`)
- [x] 3.1 `env.py` helpers: `env`, `env_bool`, `env_int`, `env_list`.
- [x] 3.2 Structured JSON logging config (`python-json-logger`) on root + celery loggers.
- [x] 3.3 `RequestIdMiddleware` + `RequestLoggingMiddleware` (request_id, method, path, status, duration_ms).

## 4. Apps and health endpoint
- [x] 4.1 Create `apps/{accounts,documents,rag,common}` packages with explicit `AppConfig`s.
- [x] 4.2 Implement `GET /api/health/` (AllowAny) returning `{"status":"ok"}` 200.
- [x] 4.3 Wire root `config/urls.py`; reserve (commented) includes for later slices.

## 5. Offline test posture
- [x] 5.1 `config/settings/test.py`: `CELERY_TASK_ALWAYS_EAGER=True`, temp Chroma persist dir, fast password hasher, stub seams.
- [x] 5.2 Ensure the suite imports no ML libraries (torch/chromadb) on the foundation path.

## 6. Tests
- [x] 6.1 Smoke: Django system check clean; `/api/health/` returns 200 `{"status":"ok"}`.
- [x] 6.2 Unit: env helpers parse bool/int/list correctly.
- [x] 6.3 Regression: feature endpoints are ABSENT (404) — they arrive in later slices.

## 7. Validate & deliver
- [x] 7.1 Create a venv, install `.[dev]`, run `python manage.py check` and `pytest` green (41 passed).
- [x] 7.2 `pre-commit run --all-files` clean.
- [x] 7.3 Author `docs/02-features/01-foundation/{test_matrix,validation-report,pull_request}.md`.
- [ ] 7.4 Open PR into `main` (stacked on slice 00); `openspec archive` after merge.
