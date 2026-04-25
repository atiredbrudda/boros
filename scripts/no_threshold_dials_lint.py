#!/usr/bin/env python3
"""Pre-commit hook: rejects threshold-dial knob names in brain/decision/.

DECIDE-04 invariant — only EV-input model parameters and breaker thresholds
(under decision.breakers.*) may be tunable. Generic `_threshold` / `_dial` /
`_cutoff` field names anywhere else under decision/ are a regression.

See [[ev-cancel-rule]].

Rationale
---------
The EV-based cancel rule is designed to be threshold-free: the formula
``EV_hold = R_share * P(no_fill) - E[loss|fill] * P(fill) - cancel_cost * P(purge)``
already self-calibrates under changing conditions. Adding a generic
``cancel_threshold`` or similar field bypasses this self-calibration and
re-introduces the threshold-dial anti-pattern that the consolidated plan
explicitly rejects.

Legitimate exceptions: breaker configuration thresholds live under
``decision.breakers.*`` in the BotConfig Pydantic schema. These are declared
in ``decision/config.py`` and the ``breakers/__init__.py`` entry points —
listed in ALLOWED_FILES below. Plan 04-03 may extend this list once the
BreakerConfig sub-models are created.

Scan strategy
-------------
The hook always walks all ``.py`` files under PROTECTED_DIRS so that both the
pre-commit normal run and ``pre-commit run --all-files`` (and direct test
invocation) see the same complete set.

Usage
-----
Pre-commit (normal operation)::

    python3 scripts/no_threshold_dials_lint.py

Direct invocation (CI / test)::

    python3 scripts/no_threshold_dials_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROTECTED_DIRS = (
    "python/src/boros_brain/decision/",
)

# ALLOWED_FILES: files that legitimately contain breaker threshold definitions.
# Plan 04-03 creates these files; add them here in the same commit so the lint
# passes after 04-03 lands.
ALLOWED_FILES: set[str] = {
    "python/src/boros_brain/decision/config.py",
    "python/src/boros_brain/decision/breakers/__init__.py",
}

# Matches: `something_threshold:`, `something_threshold =`, `something_dial:`,
# `something_dial =`, `something_cutoff:`, `something_cutoff =`.
# Word boundary \b prevents matching valid attribute access like `x.threshold`.
PATTERN = re.compile(r"\b(\w+_(?:threshold|dial|cutoff))\s*[:=]")


def _all_protected_files() -> list[Path]:
    """Return every existing .py file under PROTECTED_DIRS."""
    return [
        p
        for d in PROTECTED_DIRS
        for p in Path(d).rglob("*.py")
        if p.is_file()
    ]


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs where a threshold-dial identifier appears.

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
                f"[no_threshold_dials] {p}:{lineno}: "
                f"if this is a breaker threshold, place it in decision.breakers.* in BotConfig "
                f"(and add this file to ALLOWED_FILES) — {line.strip()[:60]}",
                file=sys.stderr,
            )
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
