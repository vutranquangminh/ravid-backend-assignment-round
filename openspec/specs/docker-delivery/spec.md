# docker-delivery Specification

## Purpose
TBD - created by archiving change s07-docker-and-delivery-compose-ci. Update Purpose after archive.
## Requirements
### Requirement: One-command containerized stack
The system SHALL be runnable via Docker Compose with all required services and health-gated startup.

#### Scenario: Compose defines the full stack
- **WHEN** the `compose.yaml` is inspected
- **THEN** it defines services for the web app, database, Redis, the Celery worker, the Chroma vector store, and an observability dashboard (Grafana)
- **AND** each long-running service declares a healthcheck and dependents wait for `service_healthy`

#### Scenario: Reviewer runs the system
- **WHEN** a reviewer copies `.env.example` to `.env`, sets an OpenRouter key, and runs `docker compose up`
- **THEN** the documented steps in the README bring up the API on the published port and the worker processes ingestion jobs

### Requirement: Production settings are environment-driven
The containerized app SHALL use a production settings module that reads configuration from the environment (Postgres, Redis, Chroma server, OpenRouter, embeddings) with `DEBUG` off by default.

#### Scenario: Chroma uses the server in Docker
- **WHEN** `CHROMA_HOST` is configured
- **THEN** the vector store connects to the Chroma server over HTTP (not a local persistent file)
- **AND** when `CHROMA_HOST` is unset (local/test) it uses the local persistent client

### Requirement: Live API documentation
The system SHALL serve browsable, generated API documentation.

#### Scenario: OpenAPI schema and Swagger UI
- **WHEN** a client requests `GET /api/schema/` and `GET /api/docs/`
- **THEN** each returns `200` — a valid OpenAPI schema and a Swagger UI respectively — without requiring authentication

### Requirement: Reproducible setup documentation
The README SHALL document how to set up and run the entire application, including the Docker commands and API-docs location.

#### Scenario: README completeness
- **WHEN** the README is read
- **THEN** it contains the run command(s), the environment setup, where to find the API docs, and how to run the tests
