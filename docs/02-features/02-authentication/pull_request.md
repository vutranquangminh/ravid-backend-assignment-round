# Pull Request — 02 Authentication (register / login / JWT)

## Progress Snapshot
- **Workstream:** 02 — authentication (RAVID Part 1)
- **Branch (source → target):** `feature/02-authentication-register-login-jwt` → `main` (direct, not stacked)
- **OpenSpec change:** `s02-authentication-register-login-jwt` (validated)
- **Status:** ready for review
- **Validation:** `manage.py check` clean · `pytest` 75 passed · `pre-commit` clean
- **Next:** slice 03 — document upload (PDF/TXT/MD)

## Summary
Email/password registration, JWT login, an authenticated-by-default access posture, and a consistent `{error}` envelope. Establishes `request.user` as the ownership key for slices 03–05.

## Scope
**In:** `apps/accounts` (register/login/me views, serializers, services), simplejwt wiring, global `IsAuthenticated`, DRF exception handler, tests.
**Out:** documents, ingestion, chat, Docker. Custom user model (using default User, email-as-username).

## Key Changes
- `apps/accounts/{serializers,services,views,urls}.py` — register (201/400), login (200/401), `GET /api/auth/me/`.
- `apps/common/exceptions.py` — reshapes DRF errors to `{"error":"<msg>"}` (400/401/403/404/405).
- `config/settings/base.py` — simplejwt auth, `IsAuthenticated` default, `SIMPLE_JWT` lifetimes, exception handler.
- `config/urls.py` — accounts routes; `tests/smoke/test_endpoints_absent.py` — register/login removed from absent set.
- `tests/integration/test_authentication_api.py`, `tests/unit/test_authentication_units.py`.

## Reviewer Steps
```bash
.venv/bin/pip install -e '.[dev]'
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
.venv/bin/python -m pytest -q              # 75 passed
pre-commit run --all-files
```
Then: register → login → call `GET /api/auth/me/` with `Authorization: Bearer <token>`.

## Validation
See `docs/02-features/02-authentication/validation-report.md`.

## Submission Readiness
- [x] OpenSpec change validated
- [x] Brief Part 1 endpoints exact (status + body + `{error}`)
- [x] Tests green (75), check clean, hooks clean
- [ ] Merged to main (awaiting review)
- [ ] `openspec archive s02-...` after merge
