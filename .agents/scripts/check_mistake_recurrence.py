#!/usr/bin/env python3
"""Warn when changed content touches keywords tied to active MISTAKE.md rules.

Ported (domain-agnostic) from the reference assessment repo. The logic is
unchanged in shape: parse the active rules out of `.agents/MISTAKE.md`, build a
haystack from the inputs, and report every active rule whose keywords appear.

Usage:

    # Explicit files (e.g. files changed in a PR):
    python .agents/scripts/check_mistake_recurrence.py path/to/changed.py ...

    # A unified diff piped on stdin (e.g. from `git diff`):
    git diff origin/main... | python .agents/scripts/check_mistake_recurrence.py -

    # No args: scan the whole repository tree (foundation-safe).
    python .agents/scripts/check_mistake_recurrence.py

Exit codes:
    0  no active mistake rule matched the input
    1  usage / environment error (e.g. MISTAKE.md missing, bad input file)
    2  at least one active mistake rule matched -> review against that rule

Pure stdlib. Robust to being run from the repo root; tolerant of a missing
MISTAKE.md (treated as exit 1 with a clear message rather than a traceback).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# scripts/ -> .agents/ -> <repo root>
ROOT = Path(__file__).resolve().parents[2]
MISTAKE_FILE = ROOT / ".agents/MISTAKE.md"

# Directories never worth scanning in the no-arg / whole-repo mode.
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "staticfiles",
    "dist",
    "build",
    ".idea",
    ".vscode",
}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".json",
    ".env",
    ".example",
    ".sh",
    ".conf",
    "",
}
TEXT_FILENAMES = {
    "Dockerfile",
    "Makefile",
    ".env",
    ".env.example",
    ".gitignore",
    "docker-compose.yml",
    "docker-compose.yaml",
}
MAX_BYTES = 2_000_000


# Matches an active-rule heading followed (anywhere before the next heading) by
# a "- Keywords:" line. Mirrors the reference regex.
RULE_RE = re.compile(
    r"^###\s+(M-\d{3}):\s+(.+?)\n(?:.*?\n)*?- Keywords:\s*(.+?)\n",
    re.MULTILINE,
)


def load_rules() -> list[tuple[str, str, list[str]]]:
    """Parse (rule_id, title, keywords) tuples from MISTAKE.md.

    Keywords are stripped of surrounding backticks and whitespace and lowered so
    matching is case- and formatting-insensitive (the ledger wraps keywords in
    backticks, e.g. `` - Keywords: `cross-user`, `leak` ``).
    """
    text = MISTAKE_FILE.read_text(encoding="utf-8")
    rules: list[tuple[str, str, list[str]]] = []
    for rule_id, title, keywords in RULE_RE.findall(text):
        parts = [
            item.strip().strip("`").strip().lower()
            for item in keywords.split(",")
            if item.strip().strip("`").strip()
        ]
        if parts:
            rules.append((rule_id, title.strip(), parts))
    return rules


def _iter_repo_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts[:-1]):
            continue
        name = path.name
        if name not in TEXT_FILENAMES and path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def build_haystack(argv: list[str]) -> tuple[str | None, str]:
    """Return (haystack, source_label), or (None, error_message) on failure."""
    args = argv[1:]

    # stdin diff mode: a single "-" argument.
    if args == ["-"]:
        data = sys.stdin.read()
        return data.lower(), "stdin diff"

    # No args: scan the whole repo tree.
    if not args:
        parts: list[str] = []
        for path in _iter_repo_text_files():
            try:
                parts.append(path.read_text(encoding="utf-8", errors="ignore").lower())
            except (OSError, UnicodeError):
                continue
        return "\n".join(parts), "repository tree"

    # Explicit file list.
    parts = []
    for raw in args:
        path = Path(raw)
        if not path.exists():
            return None, f"Missing input file: {raw}"
        try:
            parts.append(path.read_text(encoding="utf-8", errors="ignore").lower())
        except (OSError, UnicodeError) as exc:
            return None, f"Could not read input file {raw}: {exc}"
    return "\n".join(parts), f"{len(args)} file(s)"


def main(argv: list[str]) -> int:
    if not MISTAKE_FILE.exists():
        print(f"MISTAKE ledger not found at {MISTAKE_FILE}.")
        return 1

    rules = load_rules()
    if not rules:
        print("No active rules with keywords found in MISTAKE.md.")
        return 1

    haystack, source = build_haystack(argv)
    if haystack is None:
        print(source)  # source carries the error message here
        return 1

    matched: list[tuple[str, str, list[str]]] = []
    for rule_id, title, keywords in rules:
        hits = [kw for kw in keywords if kw in haystack]
        if hits:
            matched.append((rule_id, title, hits))

    print(f"Scanned {source} against {len(rules)} active mistake rule(s).")

    if not matched:
        print("No active mistake rule matched the input.")
        return 0

    print("Matched active mistake rules (review the change against each):")
    for rule_id, title, hits in matched:
        print(f"- {rule_id}: {title}  [keywords: {', '.join(hits)}]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
