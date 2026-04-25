#!/usr/bin/env python3
"""Pre-commit hook: rejects hardcoded cancel_cost scalars in brain/decision/.

The single source of truth for cancel_cost is gas_history.GasHistoryCache
(DECIDE-03). See PITFALLS #5 ([[gas-history-ewma-cancel-cost]]).

PITFALLS §C5: a hardcoded `cancel_cost = 0.5` scalar in decision/ is an
invariant violation. The gas cost must be computed from live fee_history via
EWMA so it tracks actual Arbitrum gas prices. A stale literal defeats the EV
calculation and can cause the strategy to hold orders when cancellation is
actually cheap (or to cancel when it's expensive).

Allowed exceptions
------------------
- Anything under ``python/tests/`` — tests may assert on literal values.
- ``python/src/boros_brain/decision/gas_history.py`` — the only file that
  legitimately assigns ``self.last_value_pendle = float(pendle)`` (which does
  NOT match the literal pattern ``cancel_cost(?:_pendle)? = <number>``).
  Added to ALLOWED_FILES in Plan 04-03 once that file exists.

Scan strategy
-------------
The hook always walks all ``.py`` files under PROTECTED_DIRS so that both the
pre-commit normal run and ``pre-commit run --all-files`` (and direct test
invocation) see the same complete set.

Usage
-----
Pre-commit (normal operation)::

    python3 scripts/no_hardcoded_cancel_cost_lint.py

Direct invocation (CI / test)::

    python3 scripts/no_hardcoded_cancel_cost_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROTECTED_DIRS = (
    "python/src/boros_brain/decision/",
)

# ALLOWED_FILES: initially empty.
# Plan 04-03 adds decision/gas_history.py to this set if needed — the
# single legit assignment is `self.last_value_pendle = float(pendle)` which
# does NOT match the PATTERN, so the allowlist may remain empty after 04-03.
ALLOWED_FILES: set[str] = set()

# Matches: `cancel_cost = 0.5`, `cancel_cost_pendle = 0.005`, etc.
# The word boundary \b prevents matching `_cancel_cost` sub-expressions.
PATTERN = re.compile(r"\bcancel_cost(?:_pendle)?\s*=\s*\d+\.\d+")


def _all_protected_files() -> list[Path]:
    """Return every existing .py file under PROTECTED_DIRS."""
    return [
        p
        for d in PROTECTED_DIRS
        for p in Path(d).rglob("*.py")
        if p.is_file()
    ]


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs where a hardcoded cancel_cost appears.

    Returns an empty list if the file is an allowed exception or does not exist.
    """
    s = str(path).replace("\\", "/")

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
                f"[no_hardcoded_cancel_cost] {p}:{lineno}: "
                f"use gas_history.GasHistoryCache — {line.strip()[:80]}",
                file=sys.stderr,
            )
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
