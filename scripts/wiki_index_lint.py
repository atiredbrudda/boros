#!/usr/bin/env python3
"""Wiki index completeness lint — Engineering Protocol #1 strengthening.

Enforces that every wiki page in the boros workspace is referenced **directly**
from `index.md` via a `[[wiki-link]]`. This is stricter than the LLM-Wiki
shared `orphan_detector` (which does BFS from index — a page reachable A→B→C
passes even if only A is in the index).

Why 1-hop matters: per CLAUDE.md "Where to look first", the index is the
canonical entry point. A future session that opens `index.md` should be able
to find every page without doing graph traversal.

Wiki location:
  Default: /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/
  Override: BOROS_WIKI_DIR env var

Exemptions (auto-generated artifact pages):
  - predeploy-gate-result-*.md  (one per gate run; not knowledge content)

Behavior:
  - Wiki dir missing  → exit 0 (don't break commits in environments without the wiki)
  - All pages indexed → exit 0
  - Missing pages     → exit 1, prints filenames

Run manually: python3 scripts/wiki_index_lint.py
"""
from __future__ import annotations

import fnmatch
import os
import re
import sys
from pathlib import Path

DEFAULT_WIKI_DIR = Path(
    "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki"
)

EXEMPT_GLOBS = [
    "predeploy-gate-result-*.md",  # auto-generated per-run artifacts
]

INDEX_FILENAME = "index.md"

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _normalize(s: str) -> str:
    """Canonical form for cross-matching filenames against link targets."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _extract_indexed_targets(index_path: Path) -> set[str]:
    """Return the set of normalized link targets referenced from index.md."""
    text = index_path.read_text()
    targets = set()
    for m in WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        targets.add(_normalize(target))
    return targets


def _extract_h1(page_path: Path) -> str | None:
    """Return the first H1 heading text from a wiki page, or None."""
    for line in page_path.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _is_exempt(filename: str) -> bool:
    return any(fnmatch.fnmatch(filename, pat) for pat in EXEMPT_GLOBS)


def find_missing(wiki_dir: Path) -> list[str]:
    """Return filenames of wiki pages not referenced from index.md."""
    index_path = wiki_dir / INDEX_FILENAME
    if not index_path.exists():
        print(f"wiki_index_lint: index.md not found at {index_path}", file=sys.stderr)
        return []

    indexed = _extract_indexed_targets(index_path)
    missing: list[str] = []

    for page in sorted(wiki_dir.glob("*.md")):
        if page.name == INDEX_FILENAME:
            continue
        if _is_exempt(page.name):
            continue

        slug = page.stem
        h1 = _extract_h1(page)

        candidates = {_normalize(slug)}
        if h1:
            candidates.add(_normalize(h1))

        if not (candidates & indexed):
            missing.append(page.name)

    return missing


def main() -> int:
    wiki_dir = Path(os.environ.get("BOROS_WIKI_DIR", str(DEFAULT_WIKI_DIR)))

    if not wiki_dir.exists():
        # Soft-pass: developers without the wiki checked out should not be blocked.
        print(
            f"wiki_index_lint: wiki dir not present at {wiki_dir} — skipping (set BOROS_WIKI_DIR to override)",
            file=sys.stderr,
        )
        return 0

    missing = find_missing(wiki_dir)
    if not missing:
        return 0

    print(
        f"wiki_index_lint: {len(missing)} page(s) on disk but NOT referenced from index.md:",
        file=sys.stderr,
    )
    for name in missing:
        print(f"  - {name}", file=sys.stderr)
    print(
        "\nFix: add a [[wiki-link]] for each page to index.md (Thematic section "
        "AND/OR A-Z table). See `## Maintenance` in index.md.",
        file=sys.stderr,
    )
    print(
        f"Exempt globs (auto-generated artifacts): {EXEMPT_GLOBS}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
