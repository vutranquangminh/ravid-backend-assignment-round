# Business Requirements Document

## Project

- Project name: R.A.V.I.D. Backend Assessment (RAG Document Chatbot)
- Assessment title: Take-Home Assignment - Back End Developer - Assessment & Evaluation for Full-Time Candidates - June 2026
- Assessment type: take-home backend exercise
- Issuing organization: American Tiger LLC
- Project start date: Wednesday, June 17th, 2026
- Last submission date: Saturday, June 20th, 2026

## Background

The assessment asks for the backend infrastructure of an AI chatbot. The system lets
authenticated users build a private knowledge base from their own documents and then ask
questions that are answered using only the content of their own documents. The brief frames
this as an Operations API, RAG (Retrieval-Augmented Generation), and chatbot implementation.

Concretely, the backend must:

- register and log in users, issuing JWT access tokens
- protect all knowledge-base and chat routes behind JWT authentication
- accept private document uploads (PDF, TXT, Markdown) per authenticated user
- process each upload asynchronously: extract text, chunk, embed, and index into a
  per-user isolated vector store via LangChain
- expose ingestion task status so the client can poll for completion or failure
- answer natural-language questions by retrieving the user's own document chunks and
  passing them as context to an LLM through OpenRouter, returning the answer and the
  number of tokens consumed
- maintain a simple per-user credit balance decremented by tokens consumed
- provide centralized structured logging and visualization
- run through Docker and Docker Compose

This work is intended to demonstrate backend engineering ability across API design, async
processing, RAG orchestration, per-user data isolation, observability, and delivery readiness.

## Objective

Deliver a clean, working RAG chatbot backend that satisfies the assessment requirements and
is easy for reviewers to run, inspect, and evaluate.

## Stakeholders

- Candidate: implements and documents the solution
- Reviewers: backend engineers and senior stakeholders evaluating technical quality
- End users in the assessment context: authenticated users who upload private documents and
  ask questions answered from those documents

## Business Goals

- Demonstrate practical backend implementation skills with a real RAG pipeline
- Show clean API and asynchronous task design
- Show correct per-user data isolation (one user can never read another user's documents,
  chunks, vectors, or chat answers)
- Show production-minded observability and containerized delivery
- Provide submission artifacts that minimize reviewer setup effort

## In Scope

- user registration and login with JWT issuance
- JWT-protected routes for all knowledge-base and chat operations
- document upload API accepting PDF, TXT, and Markdown only, with type and size validation
- asynchronous ingestion via Celery: text extraction, chunking, embedding, and vector indexing
- ingestion task status API for polling
- per-user isolated vector storage (one collection per user)
- RAG chat query API that retrieves owner-scoped context and answers via OpenRouter
- reporting tokens consumed per answer and decrementing a per-user credit balance
- a guard that declines to answer when no relevant context exists in the user's documents
- structured JSON logging across Django and Celery
- log aggregation and visualization via Grafana Alloy, Loki, and Grafana
- Docker Compose setup for the required services
- README and API documentation served live via OpenAPI schema (`GET /api/schema/`) and
  Swagger UI (`GET /api/docs/`)
- document management operations: list (`GET /api/documents/`) and delete
  (`DELETE /api/documents/<id>/`), owner-scoped
- a current-user identity endpoint (`GET /api/auth/me/`)
- bonus: chat continuation by chat_id, and Server-Sent Events (SSE) streaming

## Out Of Scope

- frontend application beyond what is necessary for API demonstration
- advanced user roles and permissions beyond protected versus public routes
- cross-user document sharing or collaboration features
- production cloud deployment
- paid LLM or paid embedding providers (the solution must run free of charge)
- large-scale operational hardening beyond what is reasonable for a take-home exercise

## Primary Users And Core Journeys

### Authenticated User

- registers an account
- logs in and receives a JWT access token
- uploads one or more private documents (PDF, TXT, or Markdown)
- polls ingestion status until the document is parsed, embedded, and indexed
- asks natural-language questions and receives answers grounded only in their own documents
- (bonus) continues a prior conversation, optionally with streamed responses

### Reviewer

- reads README
- runs Docker Compose
- exercises the APIs from the provided documentation
- verifies per-user isolation, async ingestion, RAG answers, and credit consumption
- verifies logs and dashboard behavior in Grafana

## Deliverables

- working backend codebase
- Docker Compose stack (web, database, Redis, Celery, vector store, observability services)
- API documentation served live via OpenAPI schema (`GET /api/schema/`) and Swagger UI (`GET /api/docs/`)
- README with setup and run instructions
- structured logging pipeline and Grafana dashboard

## Success Criteria

- required endpoints behave as specified by the brief
- protected endpoints require a valid JWT; missing or invalid tokens are rejected
- a user can only ever see and query their own documents and vectors
- document ingestion runs asynchronously and reports a task id immediately
- ingestion task status exposes processing, success, and failure clearly
- chat answers are grounded in the user's documents and report tokens consumed
- when no relevant context exists, the system says there is not enough information rather
  than fabricating an answer
- a per-user credit balance is decremented by the tokens consumed
- logs are structured and visible in Grafana
- the project can be run from documented Docker commands

## Constraints

- short delivery timeline (start June 17th, submit by June 20th, 2026)
- backend-focused assessment
- exact endpoint names from the brief must be preserved
- the solution must run completely free of charge (OpenRouter free-tier LLM, local
  open-source embeddings)
- the assessment includes ambiguous areas that must be documented as explicit defaults

## Risks

- free OpenRouter model slugs rotate and may need verification at implementation time
- OpenRouter free tier provides no embedding models, requiring a separate local embedding choice
- cross-user data leakage if vector isolation is not enforced rigorously
- ingestion failures (unparseable files, embedding errors) silently swallowed
- unbounded context sent to the LLM if retrieval is not capped
- secrets or raw document text accidentally written to logs
- delivery artifacts (README, API docs, dashboard) left too late
- observability setup complexity relative to the time box

## Working Principle

Where the assessment is unclear, the implementation chooses a pragmatic default, documents
it in the requirements baseline and in `.agents/references/assessment-decisions.md`, and
keeps the reviewer experience simple. Provider and model details are verified at
implementation time rather than answered from memory, because free model availability and
API shapes change.
