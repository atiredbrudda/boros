#!/usr/bin/env python3
"""Wiki-cite lint (INFRA-11, PROTO-03).

Any new markdown under research/, decisions/, postmortem/ (CLAUDE.md Engineering Protocol #1
write-back rule) must contain at least one [[wiki-link]] reference OUTSIDE of code blocks.

Exit 0 on clean, 1 on violation.

Usage:
  scripts/wiki_cite_lint.py <path>...   # lint specific files (from pre-commit hook)
  scripts/wiki_cite_lint.py --all       # lint all files under the policed directories
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Only markdown files under these path components are policed (per CLAUDE.md §Engineering Protocol #1)
POLICED_PATH_PARTS = ("research", "decisions", "postmortem")

WIKI_LINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks (``` ... ```) and inline code (` ... `) before searching.

    Enforces that citations appear in rendered prose, not hidden in code examples.
    """
    # Remove fenced code blocks first (greedy match is intentional for nested cases)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove inline code spans
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def has_wiki_link(md_path: Path) -> bool:
    """Return True if md_path contains at least one [[wiki-link]] outside code blocks."""
    text = md_path.read_text(encoding="utf-8")
    stripped = strip_code_blocks(text)
    return WIKI_LINK_RE.search(stripped) is not None


def is_policed(path: Path) -> bool:
    """Return True if path is a .md file under a policed directory (any component matches)."""
    return (
        path.suffix == ".md"
        and any(part in POLICED_PATH_PARTS for part in path.parts)
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Wiki-cite lint — polices research/decisions/postmortem markdown for [[wiki-link]] citations"
    )
    ap.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files to lint (pass via pre-commit hook; filters to policed paths only)",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Lint every .md under the policed directories (research/, decisions/, postmortem/)",
    )
    args = ap.parse_args()

    candidates: list[Path] = []
    if args.all:
        for part in POLICED_PATH_PARTS:
            for md in sorted(Path(".").rglob(f"{part}/**/*.md")):
                candidates.append(md)
    else:
        candidates = [p for p in args.paths if is_policed(p) and p.is_file()]

    violations: list[str] = []
    for md in candidates:
        if not has_wiki_link(md):
            violations.append(
                f"{md}: no [[wiki-link]] reference outside code blocks"
            )

    if violations:
        print("\n".join(violations), file=sys.stderr)
        print(
            f"\n{len(violations)} wiki-cite violation(s) — file a wiki page in "
            r"../LLM\ Wiki/workspaces/boros/wiki/ and cite it.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
