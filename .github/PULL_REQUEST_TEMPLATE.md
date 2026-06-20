<!-- Title: use Conventional Commits, e.g. feat(s0X): ... -->

## Summary
<!-- What does this PR deliver and why? -->

## Linked issue / workstream
Closes #
Milestone:

## Scope
**In:**
**Out:**

## Key changes
-

## Validation
```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check apps/ tests/ config/
pre-commit run --all-files
```
- [ ] `manage.py check` clean
- [ ] Full test suite green
- [ ] `ruff` + `pre-commit` clean
- [ ] Per-user isolation preserved (no cross-user data access)

## Notes for the reviewer
<!-- How to verify; anything deferred -->
