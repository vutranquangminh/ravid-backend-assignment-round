# platform-foundation Specification

## Purpose
TBD - created by archiving change s01-foundation-django-langchain-bootstrap. Update Purpose after archive.
## Requirements
### Requirement: Runnable application baseline
The system SHALL provide a bootable Django project configured with DRF and Celery, using split settings selected by `DJANGO_SETTINGS_MODULE` (default `config.settings.local`).

#### Scenario: System check passes
- **WHEN** `python manage.py check` runs against any settings module
- **THEN** it completes with no errors (exit code 0)

#### Scenario: Settings are environment-driven
- **WHEN** the application starts
- **THEN** secrets and connection strings (SECRET_KEY, DATABASE, REDIS/CELERY URLs, OpenRouter/embedding config) are read from environment variables via the env helpers, never hard-coded

### Requirement: Liveness health endpoint
The system SHALL expose `GET /api/health/` that is publicly accessible and reports process liveness without touching the database.

#### Scenario: Health returns ok
- **WHEN** a client sends `GET /api/health/`
- **THEN** the response is `200 OK` with JSON body `{"status": "ok"}`

#### Scenario: Health needs no auth
- **WHEN** `GET /api/health/` is called with no Authorization header
- **THEN** the response is still `200 OK` (the endpoint is `AllowAny`)

### Requirement: Structured request logging
The system SHALL emit structured JSON logs and attach a unique `request_id` to every HTTP request, recording method, path, status, and `duration_ms`.

#### Scenario: Each request is logged with a correlation id
- **WHEN** any HTTP request is processed
- **THEN** a JSON log line is emitted containing `request_id`, `method`, `path`, `status`, and `duration_ms`
- **AND** secrets and document contents are never included in the log

### Requirement: Offline, key-free test posture
The test settings SHALL run the whole suite without network access or API keys.

#### Scenario: Celery runs inline in tests
- **WHEN** the test suite runs under `config.settings.test`
- **THEN** Celery executes tasks eagerly (`CELERY_TASK_ALWAYS_EAGER=True`) and no external broker is required

#### Scenario: No ML/vendor calls during foundation tests
- **WHEN** the foundation test suite runs
- **THEN** it does not import heavy ML libraries (torch/chromadb) and makes no calls to embedding providers or OpenRouter

### Requirement: Feature endpoints absent until their slices
Until later slices implement them, the document and chat endpoints SHALL NOT be routable.

#### Scenario: Future endpoints are not yet served
- **WHEN** a client requests `/api/documents/upload/`, `/api/documents/status/`, `/api/chat/query/`, `/api/register/`, or `/api/login/`
- **THEN** the application does not resolve them to a successful handler (they are introduced in slices 02–05)
