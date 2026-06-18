#!/usr/bin/env python3
"""Validate the RAVID agent operating system inventory and key cross-references.

Run from the repository root:

    python .agents/scripts/validate_agents.py

Exits non-zero with an explicit message when a required `.agents/` or `docs/`
file is missing, or when a required workflow cross-reference is absent. This
script targets the FOUNDATION inventory, which exists on every branch, so it is
safe to run as a hard gate (unlike the coverage marker check, which depends on
product code that lands in later slices).
"""
from __future__ import annotations

from pathlib import Path

# scripts/ -> .agents/ -> <repo root>
ROOT = Path(__file__).resolve().parents[2]


# --- Required agent operating system files ----------------------------------
# Mirrors the FULL INTENDED FOUNDATION INVENTORY for RAVID. These all exist on
# the foundation branch and must continue to exist on every later branch.
REQUIRED_FILES = [
    # Root-level operating system / delivery anchors.
    "AGENTS.md",
    "README.md",
    ".gitignore",
    ".env.example",
    # .agents core.
    ".agents/AGENTS.md",
    ".agents/WORKFLOW.md",
    ".agents/MISTAKE.md",
    # Guidelines.
    ".agents/guidelines/ai-programming-guidelines.md",
    ".agents/guidelines/assessment-delivery-guidelines.md",
    ".agents/guidelines/code-review-guidelines.md",
    ".agents/guidelines/llm-provider-guidelines.md",
    # References (locked decisions live here canonically).
    ".agents/references/assessment-decisions.md",
    ".agents/references/assessment-validation.md",
    ".agents/references/submission-checklist.md",
    ".agents/references/source-links.md",
    # Templates.
    ".agents/templates/spec.md",
    ".agents/templates/plan.md",
    ".agents/templates/test_matrix.md",
    ".agents/templates/pull_request.md",
    ".agents/templates/pr-review.md",
    ".agents/templates/validation-report.md",
    ".agents/templates/mistake-entry.md",
    # Skills.
    ".agents/skills/agent-self-audit/SKILL.md",
    ".agents/skills/ravid-orchestrator/SKILL.md",
    ".agents/skills/django-api-delivery/SKILL.md",
    ".agents/skills/rag-ingestion-pipeline/SKILL.md",
    ".agents/skills/rag-chat-retrieval/SKILL.md",
    ".agents/skills/observability-compose-delivery/SKILL.md",
    ".agents/skills/review-mistake-guard/SKILL.md",
    # Scripts (this group).
    ".agents/scripts/validate_agents.py",
    ".agents/scripts/check_assessment_coverage.py",
    ".agents/scripts/check_mistake_recurrence.py",
    # Anchor docs.
    "docs/00-anchor/brd.md",
    "docs/00-anchor/srs.md",
    "docs/00-anchor/glossary.md",
    "docs/00-anchor/task.md",
    # Architecture docs.
    "docs/01-architecture/system_context.md",
    "docs/01-architecture/project_structure.md",
    "docs/01-architecture/database.md",
    "docs/01-architecture/docker.md",
    "docs/01-architecture/observability.md",
    "docs/01-architecture/testing.md",
    "docs/01-architecture/api_contract.yaml",
]


# --- Numbered workstreams (RAVID branch roadmap) ----------------------------
# The Phase 0 resume protocol must enumerate the numbered workstreams so a fresh
# session can reconstruct progress. These match the feature/NN-* branch roadmap.
NUMBERED_WORKSTREAMS = [
    "01-foundation",
    "02-authentication",
    "03-document-upload",
    "04-ingestion-pipeline",
    "05-rag-chat-query",
    "07-docker-and-delivery",
    "08-bonus-chat-continuation",
]


def _read(rel: str) -> str:
    """Read a repo-relative file as text, or empty string if it does not exist."""
    path = ROOT / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    # 1) Inventory existence check.
    missing: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            missing.append(rel)

    if missing:
        print("Missing required agent/docs files:")
        for item in missing:
            print(f"- {item}")
        print(
            "\nThe foundation inventory is incomplete. Create the files above "
            "before continuing."
        )
        return 1

    # 2) Cross-reference checks. The resume protocol may be split across the root
    #    AGENTS.md, the .agents/ AGENTS.md, WORKFLOW.md, and the delivery
    #    guidelines, so we search the combined text.
    workflow_text = _read(".agents/WORKFLOW.md")
    combined_resume_text = "\n".join(
        [
            _read("AGENTS.md"),
            _read(".agents/AGENTS.md"),
            workflow_text,
            _read(".agents/guidelines/assessment-delivery-guidelines.md"),
        ]
    )

    checks: list[tuple[str, str, bool]] = []

    checks.append(
        (
            "workflow references MISTAKE.md",
            "MISTAKE.md",
            "MISTAKE.md" in workflow_text,
        )
    )
    checks.append(
        (
            "workflow does not reference stale .agent/ singular path",
            ".agent/ (should be .agents/)",
            ".agent/" not in workflow_text,
        )
    )
    checks.append(
        (
            "workflow does not reference stale .agents/package path",
            ".agents/package/",
            ".agents/package/" not in workflow_text,
        )
    )
    checks.append(
        (
            "workflow does not reference stale MISTAKES.md filename",
            "MISTAKES.md (should be MISTAKE.md)",
            "MISTAKES.md" not in workflow_text,
        )
    )
    checks.append(
        (
            "resume protocol references task anchor",
            "docs/00-anchor/task.md",
            "docs/00-anchor/task.md" in combined_resume_text,
        )
    )
    checks.append(
        (
            "resume protocol references git log --decorate",
            "git log --oneline --decorate",
            "git log --oneline --decorate" in combined_resume_text,
        )
    )
    checks.append(
        (
            "resume protocol enumerates numbered workstreams",
            ", ".join(NUMBERED_WORKSTREAMS),
            all(name in combined_resume_text for name in NUMBERED_WORKSTREAMS),
        )
    )
    checks.append(
        (
            "direct-to-main exception for AGENTS.md + .agents/** is documented",
            "AGENTS.md / .agents/** -> directly to `main`",
            all(
                marker in combined_resume_text
                for marker in [
                    "AGENTS.md",
                    ".agents/**",
                    "directly to `main`",
                ]
            ),
        )
    )

    failed = [check for check in checks if not check[2]]
    if failed:
        print("Validation failed:")
        for label, target, _ in failed:
            print(f"- {label}: expected -> {target}")
        return 1

    print("Agent structure is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
