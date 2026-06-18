# Validation Report — 01 Foundation

> Branch `feature/01-foundation-django-langchain-bootstrap` (stacked on `feature/00-...`). Env: Python 3.12 venv, `.[dev]` installed (the `rag`/ML extra NOT installed — not exercised this slice).

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `python -m venv .venv && .venv/bin/pip install -e '.[dev]'` | Install core + dev deps | ✅ resolved & installed | redis 6.4.0, django 5.x, DRF, simplejwt, celery, pytest |
| `DJANGO_SETTINGS_MODULE=config.settings.test python manage.py check` | Django system check | ✅ `System check identified no issues (0 silenced).` | re-run independently by reviewer |
| `python -m pytest -q` | Full suite | ✅ `41 passed in 0.12s` | smoke + unit + regression |
| `pre-commit run --all-files` | Lint/format/hygiene | ✅ all hooks Passed (ruff auto-fixed 2 blank-line issues, re-run clean) | — |

## Failures Or Gaps

- **ML extra not installed/validated here** — `chromadb`, `langchain-huggingface`, `sentence-transformers` are declared in the `rag` extra and will be installed + exercised in slices 03/04. Intentional, to keep this slice's install/CI fast.
- **Docker/compose** not part of this slice (slice 07).
- **`django.contrib.admin`** deliberately excluded from `INSTALLED_APPS` (not needed for the assessment).
- **Real async** disabled in local/test (`CELERY_TASK_ALWAYS_EAGER=True`); real broker wiring is exercised under Docker in slice 07.

## Mistake check

`No active mistake repeated.` (M-001 path: files under `apps/`/`config/` match `project_structure.md`; M-008: middleware logs metadata only, never bodies/secrets; M-009: no provider calls in this slice.)
