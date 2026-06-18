# Pull Request Template

> One PR per feature slice, into merge-only `main`. The PR body references the OpenSpec change
> for proposal/design/tasks and the `docs/02-features/<NN-name>/` artifacts for QA/review/validation.

## Progress Snapshot

- Status:
- Current Branch:
- Last Updated:
- Current Step:
- Next Step:
- Validation State:
- PR/Merge State:

## Branches

- Source Branch: `feature/<NN-scope>`
- Target Branch: `main`

## OpenSpec Change

- Change ID: `openspec/changes/<NN-name>/`
- Proposal / Design / Tasks: linked above (do not duplicate here)

## Workstream

-

## Summary

-

## Scope

- In scope:
- Out of scope:

## Key Changes

-

## Reviewer Steps

1.
2.
3.

## Validation

- Test matrix: `docs/02-features/<NN-name>/test_matrix.md`
- Validation report: `docs/02-features/<NN-name>/validation-report.md`
- PR review: `docs/02-features/<NN-name>/pr-review.md`

## Submission Readiness

- [ ] OpenSpec change present and validates (proposal/design/tasks)
- [ ] README updated
- [ ] API docs updated (`docs/01-architecture/api_contract.yaml`)
- [ ] Docker Compose verified
- [ ] Observability verified (structured logs reach Loki/Grafana; no secrets/raw text leaked)
- [ ] Locked decisions honored (`.agents/references/assessment-decisions.md`)
- [ ] `MISTAKE.md` reviewed; no active mistake repeated
- [ ] Review completed
