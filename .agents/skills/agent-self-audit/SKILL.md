---
name: agent-self-audit
description: Run a pre-execution self-audit before substantial work in this RAVID assessment repo. Use when the repo requires a preflight check, when workflow files mention self-audit, or before implementing so the agent verifies path conventions, OpenSpec change state, task routing, coverage of skills/prompts/guidelines, required artifacts, blockers, and validation expectations.
---

# Agent Self Audit

## Purpose

Run this before substantial execution. The goal is to catch guidance gaps, path mismatches, missing workflow artifacts, missing OpenSpec changes, and task-shaping mistakes early enough to avoid bad implementation work.

This is a gate, not a report. Keep the output short and concrete, and end with a proceed/block decision.

## Session Resume

Before the audit, reconstruct repo progress in this order:

1. Check the current branch and `git status --short --branch`.
2. Read `docs/00-anchor/task.md`.
3. Inspect recent history with `git log --oneline --decorate --max-count=15`.
4. Read `docs/00-anchor/srs.md`.
5. Read `.agents/references/assessment-decisions.md`.
6. List `openspec/changes/` and read the active change's `proposal.md`, `design.md`, and `tasks.md` if a change folder for the current slice exists.
7. Inspect any non-empty files under `docs/02-features/01-foundation-django-langchain-bootstrap/` through `docs/02-features/08-bonus-chat-continuation-sse/`.
8. If requirements or terminology matter for the task, read `docs/00-anchor/brd.md`, `docs/00-anchor/srs.md`, and `docs/00-anchor/glossary.md`.

Resume rules:

- Treat `docs/00-anchor/task.md` as the intended human snapshot.
- If `task.md` conflicts with branch state or git history, report the mismatch and use repo truth.
- Treat empty workstream docs and missing OpenSpec changes as missing signal and say so explicitly.
- Map legacy or numeric branch aliases (for example `feature/foundation-*`) to the numbered RAVID workstream folders and OpenSpec change names during resume.

## Repo Path Resolution

Resolve the repo's agent control paths before auditing anything else.

1. Check for both `.agents/` and `.agent/`.
2. Prefer the path that actually exists with relevant files.
3. If both exist and disagree, prefer the path referenced by the active workflow file, then report the mismatch.
4. Confirm the OpenSpec layout: `openspec/` with `specs/` and `changes/`, plus `config.yaml` (schema `spec-driven`). The OpenSpec CLI commands are exposed as `/opsx:propose`, `/opsx:apply`, `/opsx:archive` and the `openspec-*` skills.
5. Treat naming inconsistencies as audit findings, not automatic blockers, unless they prevent safe execution.

For this repo shape, common equivalents may include:

- `.agents/skills/...` vs `.agent/...`
- `.agents/guidelines/...` vs `.agent/guidelines/...`
- `MISTAKES.md` vs `.agents/MISTAKE.md`
- per-slice proposal in `openspec/changes/<NN-name>/proposal.md` vs the older `docs/02-features/<slice>/spec.md` (spec/plan content is superseded by the OpenSpec change; reference it instead of duplicating).

## Audit Checklist

Check these items in order and keep the output short and concrete.

### 1. Task Routing

- Identify whether the work belongs to a Django app (`apps/documents`, `apps/rag`, accounts/auth), the RAG pipeline, docs, infra/observability, or the `.agents/` operating system.
- Confirm the expected working area, the matching OpenSpec change folder, and the matching `docs/02-features/<NN-name>/` delivery folder.
- Confirm whether the current git branch is valid for the task. Each feature slice gets one branch `feature/NN-<scope>` and one PR into merge-only `main`.
- If the task is feature or product work and the agent is on `main`, report that a feature branch must be created before implementation.
- If the task is limited to `AGENTS.md`, `.agents/**`, or `docs/**` foundation files, working on the foundation branch (or `main` for doc-only edits) is valid.
- If the task is obviously mis-routed, say so before coding.

### 2. Instruction Coverage

- Read the active workflow (`.agents/WORKFLOW.md`), repo agent guide (`.agents/AGENTS.md`), and relevant guidelines.
- Read `.agents/MISTAKE.md` before substantial execution.
- Confirm the OpenSpec change for the slice exists (proposal/design/tasks authored via `/opsx:propose`). If it does not, that is a finding: it must be created before `/opsx:apply` implementation work.
- Confirm whether the selected skills, prompts, templates, OpenSpec change, and repo docs actually cover the task.
- If coverage is partial, state exactly what is missing.

### 3. Artifact Expectations

OpenSpec owns the per-slice plan; `docs/02-features` owns QA/review/validation/PR artifacts. Check whether the workflow expects:

- `openspec/changes/<NN-name>/proposal.md`
- `openspec/changes/<NN-name>/design.md`
- `openspec/changes/<NN-name>/tasks.md`
- `docs/02-features/<NN-name>/test_matrix.md`
- `docs/02-features/<NN-name>/pr-review.md`
- `docs/02-features/<NN-name>/validation-report.md`
- `docs/02-features/<NN-name>/pull_request.md`

Do not create them during the audit unless the task explicitly asks for setup or documentation work. Just report what will be required later.

### 4. Boundary And Risk Scan

- Identify app boundary issues (`apps/documents` vs `apps/rag`).
- Identify business-rule or design ambiguity, especially around the locked decisions (per-user vector isolation, 404-not-403 leak rule, no-relevant-context guard, credit deduction, secret/document-text safety).
- Identify missing dependencies, environments, or tool approvals (Redis, Postgres, Chroma, OpenRouter key, local HuggingFace embedding model download).
- Identify validation risks such as missing tests, unclear acceptance criteria, or absent PDF/TXT/MD fixtures.
- Identify whether the task is covered by `docs/00-anchor/srs.md`, the OpenSpec change, and `.agents/references/assessment-decisions.md`.

### 5. Proceed / Block Decision

Classify the result as one of:

- `proceed`: no blocker; continue with noted assumptions
- `proceed_with_risks`: non-blocking gaps exist; continue while surfacing them
- `blocked`: a real blocker prevents safe execution

Only ask the user questions when the issue is genuinely blocking or the tradeoff is high impact.

## Output Format

Return a concise audit with these sections when relevant:

- `Task`: what you believe the user wants
- `Current branch`: branch name and cleanliness
- `Resume sources checked`: branch status, `task.md`, git history, assessment docs, OpenSpec changes, and non-empty workstream docs
- `Current workstream`: numbered workstream or `none identified`
- `OpenSpec change`: change folder name and whether proposal/design/tasks exist
- `Completed workstreams`: list or `no non-empty workstream docs yet`
- `Routing`: where the work belongs
- `Coverage`: what instructions/docs/skills/OpenSpec change cover it
- `Mistakes`: active mistake rules that are relevant (for example M-005 cross-user vector leakage)
- `Open conflicts`: doc/repo mismatches or `none`
- `Findings`: mismatches, missing artifacts, or risks
- `Decision`: `proceed`, `proceed_with_risks`, or `blocked`
- `Next step`: the immediate action you will take

Prefer bullets over prose. Do not turn the audit into a long report.

## Default Behaviors

- Make reasonable assumptions when gaps are minor and reversible.
- Prefer repo truth over stale workflow text.
- Do not block on naming inconsistencies alone.
- If a referenced path is missing but an obvious equivalent exists, use the equivalent and report it.
- If guidance conflicts, name the conflict explicitly and follow the most local, task-relevant source (OpenSpec change > workstream docs > general guidelines) unless that creates risk.

## Example Triggers

Use this skill when the user or repo asks for any of the following:

- "run self-audit"
- "preflight this task"
- "check if the workflow covers this"
- workflow text says to run `agent-self-audit` before implementation
- the repo has custom agent docs and you are about to do substantial work
