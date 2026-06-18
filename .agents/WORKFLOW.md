# Agent Workflow

Use this workflow for all substantial work in this repository. The goal is fast delivery with explicit decisions, repeatable validation, and a mandatory feedback loop from review findings into `.agents/MISTAKE.md`.

RAVID runs a **hybrid OpenSpec workflow**. The 7-phase pipeline below is unchanged in shape from a standard delivery pipeline, but three phases are wired into the OpenSpec CLI:

- **Phase 1 (Spec)** authors the per-feature OpenSpec change with `/opsx:propose` -> `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}`.
- **Phase 3 (Implementation)** drives the implementation with `/opsx:apply`, working the steps in `tasks.md`.
- **Phase 6 (Finalization)** archives the change with `/opsx:archive` after the PR merges.

OpenSpec owns proposal/design/tasks. `docs/02-features/<NN-name>/` owns the QA/review/validation/PR artifacts (`test_matrix.md`, `pr-review.md`, `validation-report.md`, `pull_request.md`). The `spec.md`/`plan.md` templates are superseded by the OpenSpec `proposal.md`/`design.md`/`tasks.md`; reference them rather than duplicating.

## Phase 0: Session Resume

Run this before planning or coding in every fresh AI session.

1. Check the current branch and `git status --short --branch`.
2. Read `docs/00-anchor/task.md`.
3. Inspect recent history with `git log --oneline --decorate --max-count=15`.
4. Read `docs/00-anchor/srs.md`.
5. Read `.agents/references/assessment-decisions.md`.
6. List active OpenSpec changes with `openspec list --json`; read the active change's `openspec/changes/<NN-name>/{proposal,design,tasks}.md`.
7. Inspect any non-empty files under:
   - `docs/02-features/01-foundation/`
   - `docs/02-features/02-authentication/`
   - `docs/02-features/03-document-upload/`
   - `docs/02-features/04-ingestion-pipeline/`
   - `docs/02-features/05-rag-chat-query/`
   - `docs/02-features/07-docker-and-delivery/`
   - `docs/02-features/08-bonus-chat-continuation-sse/`
8. If the active task depends on requirements or terminology, read:
   - `docs/00-anchor/brd.md`
   - `docs/00-anchor/srs.md`
   - `docs/00-anchor/glossary.md`

Resume rules:

- `docs/00-anchor/task.md` is the intended human snapshot.
- If `task.md` conflicts with branch state, git history, or `openspec/changes/`, report the mismatch and use repo truth for execution until the docs are updated.
- Treat empty files under `docs/02-features/` as missing progress signal and say so explicitly instead of inferring progress.
- A workstream counts as complete only when its OpenSpec change is archived AND its `docs/02-features/<NN>/` artifacts exist.
- Map legacy/CSV workstream aliases when resuming from older branches:
  - `foundation` -> `01-foundation`
  - `authentication` -> `02-authentication`
  - `csv-upload` / `files` -> `03-document-upload`
  - `processing-pipeline` / `operations` -> `04-ingestion-pipeline`
  - `task-status` -> folded into the `03`/`04` status endpoint
  - `perform-operation` -> `05-rag-chat-query`
  - `observability` -> folded into `07-docker-and-delivery`
  - `docker-and-delivery` -> `07-docker-and-delivery`

Required resume output:

- current branch
- resume sources checked
- current workstream and active OpenSpec change
- completed workstreams
- latest validated state
- next intended task
- open doc/repo/openspec conflicts

## Required Read Order

Before substantial work, read in this order:

1. `.agents/AGENTS.md`
2. `.agents/WORKFLOW.md`
3. `.agents/MISTAKE.md`
4. `docs/00-anchor/task.md`
5. `docs/00-anchor/srs.md`
6. `.agents/references/assessment-decisions.md`
7. The active OpenSpec change `openspec/changes/<NN-name>/{proposal,design,tasks}.md`
8. The relevant skill in `.agents/skills/`
9. The active workstream artifacts in `docs/02-features/<NN-name>/`
10. `docs/00-anchor/brd.md`, `docs/00-anchor/srs.md`, and `docs/00-anchor/glossary.md` when the task depends on requirements or terminology

## Preflight

Complete this before planning or coding:

- Complete Phase 0 session resume and surface any doc/repo/openspec mismatch before continuing.
- Route the task to the correct workstream and OpenSpec change.
- Confirm the current git branch is appropriate for the task.
- If the task is feature or product work, create a new branch from the latest `main` before editing.
- Do not continue feature or product development on `main`.
- If the task is limited to `AGENTS.md` and `.agents/**`, direct work on `main` is allowed (the `.agents`-direct-to-main exception).
- Run `.agents/skills/agent-self-audit/SKILL.md`.
- Read `.agents/MISTAKE.md` and note any active rules relevant to the task (RAG-specific: M-005 isolation, M-006 swallowed failures, M-007 unbounded context, M-008 secret/raw-text logging, M-009 provider details from memory).
- Validate that the selected skills, opsx commands, guidelines, templates, and references cover the task.
- Validate the task against `docs/00-anchor/srs.md` and `.agents/references/assessment-decisions.md`.
- If the current workstream artifacts are empty, state that and fall back to `docs/00-anchor/task.md`, the OpenSpec change, plus git history for progress reconstruction.
- Surface missing constraints, design conflicts, package or app boundary issues, and documentation gaps before implementation.
- Stop only if a real blocker remains after codebase analysis.

## Phase 1: Requirements And Spec (OpenSpec `/opsx:propose`)

- Clarify scope, dependencies, edge cases, acceptance criteria, and non-goals.
- Use planning discussion before coding when useful.
- Author the per-feature OpenSpec change by running `/opsx:propose` (or `openspec new change "<NN-name>"`), producing:
  - `openspec/changes/<NN-name>/proposal.md` (what & why)
  - `openspec/changes/<NN-name>/design.md` (how)
  - `openspec/changes/<NN-name>/tasks.md` (implementation steps)
- The OpenSpec change is the implementation contract for the current workstream. Do NOT duplicate it into `spec.md`/`plan.md`; those templates only point at the OpenSpec artifacts.
- Create the matching delivery folder `docs/02-features/<NN-name>/` for QA/review/validation/PR artifacts.
- Keep the feature branch name aligned with the current workstream using `feature/<nn-workstream>-<short-scope>`.
- Record every non-obvious decision in the OpenSpec change and/or `.agents/references/assessment-decisions.md`, not only in chat.
- If the assessment brief is ambiguous, lock the default in `.agents/references/assessment-decisions.md` before implementation proceeds (M-003).

## Phase 2: Plan And Test Matrix

- Ensure `openspec/changes/<NN-name>/tasks.md` lists atomic, commit-sized steps. (`tasks.md` replaces the standalone `plan.md`.)
- Create or update `test_matrix.md` in `docs/02-features/<NN-name>/` covering:
  - happy path
  - validation (upload type/size, payload shape, error envelope)
  - auth (JWT required, 401 on missing/invalid token)
  - ownership/isolation (cross-user access returns 404; per-user Chroma collection scoping)
  - async and task-state behavior (PROCESSING/SUCCESS/FAILURE, failure surfaced)
  - RAG behavior (retrieval top_k, no-context guard, real tokens_consumed, credit decrement)
  - observability (structured JSON logs, no secrets/raw text)
  - docker startup and health
  - regression risk
- Define validation commands and expected outcomes for every implementation step.
- Before each step, re-check active mistake rules that apply to the area being changed.

## Phase 3: Implementation (OpenSpec `/opsx:apply`)

- Drive implementation with `/opsx:apply <NN-name>`, working the steps in `openspec/changes/<NN-name>/tasks.md` one at a time.
- Implement one planned step at a time.
- Prefer test-first for new behavior and bug fixes.
- For each step: code -> validate -> document -> commit -> mark the step done in `tasks.md`.
- Do not batch multiple planned steps into one commit.
- Keep changes traceable across code, the OpenSpec change, docs, tests, and delivery artifacts.
- If a mistake rule is triggered during implementation, stop and fix the underlying pattern before continuing.

## Phase 4: Review And Refactor

Review is mandatory before final submission or merge-like completion.

- Read `.agents/MISTAKE.md` again before reviewing code.
- Review the diff against the intended scope (the OpenSpec proposal/design), not just for style.
- Use `.agents/guidelines/code-review-guidelines.md`.
- Create or update `pr-review.md` in `docs/02-features/<NN-name>/` with:
  - findings ordered by severity
  - open questions
  - residual risks
  - recommendation
- Explicitly state whether any active mistake rule was repeated.
- If a new recurring issue class is found, add it to `.agents/MISTAKE.md`.
- If an issue is a one-off incident but not yet a recurring rule, add it under `New Incidents` in `.agents/MISTAKE.md`.
- Apply refactors and rerun relevant validation before moving on.

## Phase 5: Full Validation

Run the full validation set before finalization:

- unit and integration tests
- API smoke tests (register, login, upload, status, chat query)
- auth smoke tests (401 on missing/invalid JWT)
- ownership/isolation smoke tests (cross-user document/task/vector access returns 404)
- Celery worker and task-status smoke tests (ingestion success and induced failure both surface correctly)
- RAG smoke tests (grounded answer, no-context guard, real tokens_consumed from `usage`, credit decrement)
- structured logging smoke tests (logs present in Grafana via Alloy -> Loki; no secrets or raw document text)
- Docker Compose healthchecks and startup ordering
- documentation artifact checks (README, API docs, OpenSpec change present)

Create or update `validation-report.md` in `docs/02-features/<NN-name>/` with commands, results, evidence, and unresolved items.

## Phase 6: Finalization And Submission Prep (OpenSpec `/opsx:archive`)

- Create or update `pull_request.md` in `docs/02-features/<NN-name>/` with summary, scope, reviewer instructions, and checklist.
- Ensure README, API docs, and assessment-specific docs are current.
- Run `.agents/scripts/check_assessment_coverage.py`.
- Run `.agents/scripts/validate_agents.py`.
- Run `.agents/scripts/check_mistake_recurrence.py`.
- Open a pull request from the feature branch into `main` for feature and product work.
- Do not merge feature or product work into `main` without a pull request.
- After the PR merges, archive the OpenSpec change by running `/opsx:archive <NN-name>` (moves it out of active `openspec/changes/`).
- For agent operating system maintenance limited to `AGENTS.md` and `.agents/**`, direct commits to `main` are allowed if the change is isolated from product work.
- Confirm no open blocker remains.

## Review To Mistake Loop

This loop is mandatory:

1. Read `MISTAKE.md` before implementation in a risky area.
2. Read `MISTAKE.md` again before review.
3. During review, check for repeated mistake rules.
4. If a new mistake class appears, write it down immediately.
5. Future implementation and review must consult those rules first.

No review is complete unless it states exactly one of:

- `No active mistake repeated.`
- `Repeated mistake: M-XXX`

## Clarification Standard

- Ask only blocking questions.
- Provide 2-4 concrete options.
- Put the recommended option first.
- Explain tradeoffs and likely impact.
- If the agent can proceed safely with the recommended option, say so explicitly.

## Always-On Gates

- Follow `.agents/guidelines/ai-programming-guidelines.md`.
- Follow `.agents/guidelines/code-review-guidelines.md` during review.
- Follow `.agents/guidelines/assessment-delivery-guidelines.md` for assessment-specific tradeoffs.
- Follow `.agents/guidelines/llm-provider-guidelines.md` for any OpenRouter/embedding/provider work; never answer provider/model details from memory (M-009).
- Keep clear architecture boundaries (`apps/documents`, `apps/rag`).
- Validate external input and handle failures explicitly; surface ingestion failures in both logs and task status (M-006).
- Enforce per-user vector isolation on every retrieval (M-005).
- Bound LLM context to the retrieved `top_k` chunks (M-007).
- Never log secrets, tokens, passwords, API keys, or full sensitive payloads / raw document text (M-008).
- Keep docs, tests, the OpenSpec change, and delivery artifacts aligned with code changes.
