---
name: observability-compose-delivery
description: Deliver structured observability and Docker Compose setup for the RAVID assessment. Use when implementing JSON logging, Celery/ingestion task metadata logs, RAG log fields, Alloy and Loki config, Grafana provisioning, Docker Compose services (including Chroma), startup ordering, healthchecks, README run instructions, API documentation hooks, or final assessment delivery artifacts.
---

# Observability Compose Delivery

## Purpose

Use this skill for logging, dashboarding, container orchestration, and final delivery artifacts.

## Read Before Work

1. `.agents/MISTAKE.md`
2. `.agents/guidelines/assessment-delivery-guidelines.md`
3. `.agents/references/assessment-decisions.md`
4. `.agents/references/submission-checklist.md`
5. The active `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}`
6. `docs/02-features/<NN-name>/test_matrix.md`

## Scope

- Django JSON logs
- Celery / `IngestionJob` JSON logs
- RAG retrieval and chat JSON logs
- Alloy configuration
- Loki configuration
- Grafana datasource and dashboard provisioning
- Docker Compose services (web, worker, Redis, Postgres, Chroma, Alloy, Loki, Grafana)
- healthchecks and startup order
- README run instructions
- API documentation delivery hooks

## RAG Log Fields

Ship structured JSON logs that make Django, Celery, and RAG streams distinguishable and traceable. Include fields such as:

- service / component label (web vs worker vs rag)
- `user_id`, `document_id`, `task_id`, `chat_id` where applicable
- ingestion: chunk count, status (`PROCESSING|SUCCESS|FAILURE`), durations
- chat: retrieved chunk count, `tokens_consumed`, credit delta, model slug used
- error class and safe message on failures

Never log raw document text, raw chunk text, JWTs, the OpenRouter key, or embedding keys (M-008). Embedding/parse failures must appear in the logs in addition to the task-status API (M-006).

## Rules

- Use Grafana Alloy instead of Promtail.
- Keep dashboard and datasource provisioning in version control.
- Include service labels or fields that make Django, Celery, and RAG log streams easy to distinguish.
- Add the Chroma service to Docker Compose alongside Redis, Postgres, web, and worker, with correct startup ordering and healthchecks.
- Validate Docker startup order explicitly (Postgres/Redis/Chroma healthy before web/worker).
- Do not leave README or API documentation for the final hour (M-004: delivery artifacts deferred).

## Required Checks

- JSON logging fields present (including RAG fields)
- log shipping path works (Django + Celery -> Alloy -> Loki -> Grafana)
- Grafana dashboard provisioning works
- Docker services are bootable in the intended order (incl. Chroma)
- Healthchecks gate dependent services
- README and API docs match the actual run path
- No secret or raw document text appears in shipped logs

## Output

When this skill is used, the result should include:

- updated observability config (logging, Alloy, Loki, Grafana)
- updated Docker config (incl. Chroma service)
- updated README or API docs as needed
- updated `docs/02-features/<NN-name>/test_matrix.md` if coverage changed
- validation evidence
