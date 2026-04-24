#!/usr/bin/env python3
"""Pre-commit hook: rejects ``time.time()`` in brain/{decision,data,screener,fill_model,loss_model,reward_model,sizer}/.

PITFALLS §C7 (clock drift during macOS sleep/wake): comparing to ``time.time()``
silently miscomputes oracle-staleness breakers and fIndex ``fTime`` comparisons
when the OS clock is skewed after sleep/wake.  The only clock that matters for
chain-time decisions is ``chain_time.now_cached()``.

Allowed exceptions
------------------
- ``python/src/boros_brain/data/chain_time.py`` — this file deliberately uses
  ``time.time()`` to *measure* the difference between wall-clock and chain-time.
- Anything under ``python/tests/`` — tests need wall-clock (e.g. TTL assertions).

Scan strategy
-------------
The hook always walks all ``.py`` files under PROTECTED_DIRS so that both the
pre-commit normal run and ``pre-commit run --all-files`` (and direct test
invocation) see the same complete set.  This catches violations whether the file
is newly staged, already committed, or written-but-not-yet-staged.

Usage
-----
Pre-commit (normal operation)::

    python3 scripts/no_time_time_lint.py

Direct invocation (CI / test)::

    python3 scripts/no_time_time_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROTECTED_DIRS = (
    "python/src/boros_brain/decision/",
    "python/src/boros_brain/data/",
    "python/src/boros_brain/screener/",
    "python/src/boros_brain/fill_model/",
    "python/src/boros_brain/loss_model/",     # Phase 3 Plan 03-04
    "python/src/boros_brain/reward_model/",   # Phase 3 Plan 03-04
    "python/src/boros_brain/sizer/",          # Phase 3 Plan 03-04
)

# chain_time.py is explicitly allowed — it measures wall-clock vs chain-time.
ALLOWED_FILES = {
    "python/src/boros_brain/data/chain_time.py",
}

PATTERN = re.compile(r"\btime\.time\s*\(")


def _all_protected_files() -> list[Path]:
    """Return every existing .py file under PROTECTED_DIRS."""
    return [
        p
        for d in PROTECTED_DIRS
        for p in Path(d).rglob("*.py")
        if p.is_file()
    ]


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs where ``time.time()`` appears in *path*.

    Returns an empty list if the file is an allowed exception or does not exist.
    """
    s = str(path).replace("\\", "/")

    # Skip explicitly allowed files.
    if s in ALLOWED_FILES:
        return []

    if not path.is_file():
        return []

    hits: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        if PATTERN.search(line):
            hits.append((i, line))
    return hits


def main() -> int:
    """Entry point — returns 0 on success, 1 if violations found."""
    fail = 0
    for p in _all_protected_files():
        for lineno, line in _scan(p):
            print(
                f"[no_time_time] {p}:{lineno}: "
                f"use chain_time.now_cached() — {line.strip()[:80]}",
                file=sys.stderr,
            )
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
