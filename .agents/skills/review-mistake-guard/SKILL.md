---
name: review-mistake-guard
description: Run review passes that are mistake-aware for the RAVID assessment repo. Use when reviewing any substantial code or documentation change so the agent reads MISTAKE.md first, checks for repeated failure patterns, reports findings before summary, and updates the mistake ledger when a new recurring issue class is discovered.
---

# Review Mistake Guard

## Purpose

Use this skill for every substantial review in this repo. It enforces the review-to-mistake loop: read the ledger first, find issues, state whether any active mistake was repeated, and record new recurring issue classes.

## Required Read Order

1. `.agents/MISTAKE.md`
2. `.agents/guidelines/code-review-guidelines.md`
3. `docs/00-anchor/srs.md`
4. The active `openspec/changes/<NN-name>/{proposal.md,design.md,tasks.md}` for the slice under review
5. `docs/02-features/<NN-name>/pr-review.md` if it exists
6. the diff or changed files

## Required Behavior

- Findings must come first.
- Focus on bugs, regressions, requirement misses, missing tests, delivery gaps, and repeated mistakes.
- Explicitly state one of:
  - `No active mistake repeated.`
  - `Repeated mistake: M-XXX`
- If a new recurring issue class is found:
  - update `.agents/MISTAKE.md`
  - mention the added entry in the review

## Active Mistake Rules To Check

In addition to the ported reference rules (M-001 path drift, M-002 review without MISTAKE, M-003 silent ambiguity, M-004 delivery artifacts deferred), check the RAG-specific rules:

- M-005 cross-user vector/chunk leakage (retrieval and upsert scoped to `user_{user_id}`; cross-user access returns 404)
- M-006 embedding/parse failure swallowed (must surface in BOTH logs and task-status)
- M-007 unbounded context sent to the LLM (bounded by `top_k=4`)
- M-008 OpenRouter/embedding key or raw document text logged
- M-009 provider/model details answered from memory instead of verified

## Review Checklist

- Assessment contract still holds (endpoint paths, error envelope, status codes)
- 404-not-403 leak rule and 401 auth behavior preserved
- `tokens_consumed` read from `usage`, credit deducted correctly
- No-relevant-context guard present where applicable
- Public API changes are documented (OpenSpec change + `api_contract.yaml`)
- Tests cover the changed behavior
- Docker and observability implications are considered when relevant (incl. Chroma service, RAG log fields)
- No secret or raw document text in logs
- Active mistake rules were checked

## Output

Return:

- findings
- open questions or assumptions
- residual risks
- mistake check result (`No active mistake repeated.` or `Repeated mistake: M-XXX`)
- brief summary
