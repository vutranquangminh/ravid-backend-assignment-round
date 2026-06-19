# Test Matrix — 02 Authentication (register / login / JWT)

> Spec: `openspec/changes/s02-authentication-register-login-jwt/`. Implements RAVID Part 1. Settings: `config.settings.test`.

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Happy | Register new user | Integration | `201 {message, user_id}` | `tests/integration/test_authentication_api.py` |
| Happy | Login valid creds | Integration | `200 {message, token}` (non-empty JWT) | `test_authentication_api.py` |
| Happy | `GET /api/auth/me/` with token | Integration | `200 {user_id, email}` | `test_authentication_api.py` |
| Validation | Duplicate email | Integration | `400 {"error":"User with this email already exists."}` | `test_authentication_api.py` |
| Validation | Malformed email / password < 8 | Integration | `400 {"error":"<msg>"}` | `test_authentication_api.py` |
| Validation | Serializer + service units | Unit | correct accept/reject | `tests/unit/test_authentication_units.py` |
| Auth | Login wrong password / unknown email | Integration | `401 {"error":"Invalid email or password"}` | `test_authentication_api.py` |
| Auth | Protected route without token | Integration | `401 {"error":"..."}` (envelope) | `test_authentication_api.py` |
| Auth | Public routes open (health/register/login) | Integration | not rejected for missing auth | `test_authentication_api.py`, slice-01 smoke |
| Async | (n/a this slice) | — | — | — |
| Observability | request_id + duration_ms still logged | Inherited | JSON log per request | slice-01 middleware unchanged |
| Docker | (deferred to slice 07) | — | — | — |
| Regression | upload/status/chat still ABSENT | Smoke | `404` | `tests/smoke/test_endpoints_absent.py` (register/login removed — now present) |
| Hygiene | lint/format/commit hooks | Local | all pass | `pre-commit run --all-files` |

**Total:** 75 tests pass (60 new for auth + 15 prior). No ML imports; fully offline.
