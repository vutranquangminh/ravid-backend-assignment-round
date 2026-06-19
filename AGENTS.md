# Agents Entry Guide

Start here before using anything in `.agents/`, `openspec/`, or `.claude/`.

This repository delivers **RAVID** — a Retrieval-Augmented Generation (RAG) document chatbot backend (Django + DRF + Celery + Chroma + LangChain + OpenRouter) as a take-home assessment. The agent operating system lives in `.agents/`, the spec-driven change workflow lives in `openspec/` (driven by `/opsx:*` commands in `.claude/commands/opsx/`), and the human-facing docs live in `docs/`.

## Entry Flow

1. Read [`./.agents/AGENTS.md`](./.agents/AGENTS.md) — the operating-system guide, source-of-truth precedence, and Git workflow.
2. Read [`./.agents/WORKFLOW.md`](./.agents/WORKFLOW.md) — the 7-phase pipeline, the hybrid OpenSpec integration, and the review-to-mistake loop.
3. Read [`./.agents/MISTAKE.md`](./.agents/MISTAKE.md) — the live ledger of avoidable failure patterns (M-001 .. M-009).

## Two Workflows, One Discipline (Hybrid OpenSpec)

RAVID runs a **hybrid** workflow. Hold both halves in mind:

- **OpenSpec owns the per-feature contract.** Each feature slice is an OpenSpec change under `openspec/changes/<NN-name>/` containing `proposal.md` (what & why), `design.md` (how), and `tasks.md` (implementation steps). These are authored with `/opsx:propose`, implemented with `/opsx:apply`, and archived with `/opsx:archive` after merge. The OpenSpec CLI is installed and initialized (`openspec/` with `specs/` + `changes/`, `config.yaml` schema `spec-driven`).
- **`.agents/` + `docs/02-features/` own the delivery discipline.** One git branch `feature/NN-<scope>` per slice, one PR into merge-only `main`, and the QA/review/validation/PR artifacts under `docs/02-features/<NN-name>/` (`test_matrix.md`, `pr-review.md`, `validation-report.md`, `pull_request.md`).

Precedence between them: `openspec/changes/<NN>/{proposal,design,tasks}.md` supersedes the older `spec.md` / `plan.md` template content. Where a template mentions `spec.md`/`plan.md`, reference the OpenSpec artifacts instead of duplicating them.

## Session Resume

Before planning or coding in a fresh AI session, run this resume pass in order:

1. Check the current branch and `git status --short --branch`.
2. Read [`docs/00-anchor/task.md`](./docs/00-anchor/task.md).
3. Inspect recent history with `git log --oneline --decorate --max-count=15`.
4. Read [`docs/00-anchor/srs.md`](./docs/00-anchor/srs.md).
5. Read [`.agents/references/assessment-decisions.md`](./.agents/references/assessment-decisions.md).
6. List active OpenSpec changes with `openspec list --json` and read the active change's `openspec/changes/<NN-name>/{proposal,design,tasks}.md`.
7. Read any non-empty workstream artifacts under `docs/02-features/`:
   - `01-foundation`
   - `02-authentication`
   - `03-document-upload`
   - `04-ingestion-pipeline`
   - `05-rag-chat-query`
   - `07-docker-and-delivery`
   - `08-bonus-chat-continuation-sse`
8. If the active task depends on requirements or terminology, also read:
   - [`docs/00-anchor/brd.md`](./docs/00-anchor/brd.md)
   - [`docs/00-anchor/srs.md`](./docs/00-anchor/srs.md)
   - [`docs/00-anchor/glossary.md`](./docs/00-anchor/glossary.md)

Required resume outcome:

- current branch
- current workstream and active OpenSpec change
- completed workstreams
- latest validated state
- next intended task
- any doc/repo/openspec mismatches

Conflict rule:

- `docs/00-anchor/task.md` is the intended human snapshot.
- If `task.md` conflicts with branch state, git history, or `openspec/changes/`, report the mismatch and use repo truth for execution until the docs are updated.

## Preflight Validation

Before doing substantial work:

1. Validate that the session resume outcome is current and explicit.
2. Validate that the chosen skill, opsx command, guidelines, and references cover the task.
3. Validate that required workflow artifacts/templates and the OpenSpec change exist.
4. Validate whether any business-rule, design, or boundary ambiguity blocks execution.
5. If the guidance is insufficient or conflicting, stop and report the gap before continuing.

## Autonomy Rule

- Run autonomously until blocked.
- Stop only for real blockers:
  - missing business constraints,
  - design ambiguity,
  - compatibility uncertainty,
  - dependency/setup approval,
  - conflicting guidance.

## Clarification Standard

When asking clarifying questions, always provide options.

- Give 2-4 concrete options.
- Put the recommended option first and label it clearly.
- Explain each option briefly:
  - what it means,
  - tradeoff,
  - likely impact.
- Ask only blocking questions, not preference noise.

## Source of Truth

- `.agents/` is the operating system for the agents.
- `openspec/changes/<NN-name>/` holds the per-feature contract (proposal, design, tasks).
- `docs/02-features/<NN-name>/` is the required location for QA/review/validation/PR artifacts.
- `.agents/references/assessment-decisions.md` holds the locked decisions for the assessment.
- Active workstream folders / OpenSpec change slices are:
  - `01-foundation`
  - `02-authentication`
  - `03-document-upload`
  - `04-ingestion-pipeline`
  - `05-rag-chat-query`
  - `07-docker-and-delivery`
  - `08-bonus-chat-continuation-sse`
- `main` is merge-only for feature and product work; each feature must use its own branch and PR back into `main`.
- Changes limited to `AGENTS.md` and `.agents/**` may be committed directly to `main`.
- Keep code, OpenSpec change, docs, validation, and PR artifacts in sync.
