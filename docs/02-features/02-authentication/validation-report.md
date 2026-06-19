# Validation Report — 02 Authentication

> Branch `feature/02-authentication-register-login-jwt` (base `main`). Env: `.venv`, `.[dev]`.

## Results

| Command | Purpose | Result | Evidence |
|---------|---------|--------|----------|
| `manage.py check` | Django system check | ✅ `System check identified no issues (0 silenced).` | re-run independently |
| `python -m pytest -q` | Full suite | ✅ `75 passed` | 60 new auth tests + 15 prior |
| `makemigrations --check --dry-run` | Migration state | ✅ no pending model migrations (default User, no custom models) | — |
| `pre-commit run --all-files` | Lint/format/hooks | ✅ all pass (ruff auto-formatted, re-run clean) | — |

## Brief compliance (Part 1)

| Endpoint | Brief | Implemented |
|----------|-------|-------------|
| `POST /api/register/` | 201 `{message,user_id}` / 400 `{error}` | ✅ exact |
| `POST /api/login/` | 200 `{message,token}` / 401 `{error}` | ✅ exact |
| JWT middleware | `Authorization: Bearer <token>` protects routes | ✅ global `IsAuthenticated` + simplejwt |

## Failures Or Gaps

- **Login serializer-invalid body returns 401** (not 400) — deliberate: any unparseable login body is treated as bad credentials with the unambiguous `{"error":"Invalid email or password"}` (documented in design D-…).
- **No custom user model** (default Django User, email-as-username) — locked decision; documented.
- Documents/ingestion/chat still absent (own slices); regression asserts 404.

## Mistake check

`No active mistake repeated.` (M-003: ambiguities locked in assessment-decisions before coding; envelope consistency via the exception handler; M-008: no secrets/passwords logged — middleware logs metadata only.)
