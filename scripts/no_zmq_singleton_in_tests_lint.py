#!/usr/bin/env python3
"""Pre-commit hook: rejects zmq.asyncio.Context.instance() under python/tests/.

Wave-0 prerequisite — ZMQ Fixture Leak fix (Plan 05-01).

The singleton pattern `zmq.asyncio.Context.instance()` in test files creates
a process-wide shared context across parametrize iterations and test files.
Across a 300+ test collection the leftover routing state causes `bind()` to
deadlock indefinitely — the full-suite-green invariant (BACK-07 success criterion #6)
cannot be satisfied with the singleton present anywhere under python/tests/.

The correct pattern is per-test Context() with explicit teardown:

    ctx = zmq.asyncio.Context()        # NOT Context.instance()
    try:
        sock = ctx.socket(zmq.PULL)
        sock.connect(endpoint)         # CONNECT; the production bus owns bind()
        # ... test body ...
        sock.close()
    finally:
        ctx.term()                     # MUST term, not just close

See [[wave-0-zmq-fixture-leak-fix]] for root cause analysis and the Phase 4
carried-over hang this guard prevents from recurring.

Scan strategy
-------------
The hook always walks all ``.py`` files under PROTECTED_DIRS so that both the
pre-commit normal run and ``pre-commit run --all-files`` (and direct test
invocation) see the same complete set.

Usage
-----
Pre-commit (normal operation)::

    python3 scripts/no_zmq_singleton_in_tests_lint.py

Direct invocation (CI / test)::

    python3 scripts/no_zmq_singleton_in_tests_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROTECTED_DIRS = (
    "python/tests/",
)

# The lint-test file itself is allowed: it contains Context.instance() only in
# docstrings and injected string literals (not live code), and tests the lint behavior.
ALLOWED_FILES: set[str] = {
    "python/tests/test_no_zmq_singleton_in_tests_lint.py",
}

# Matches: zmq.asyncio.Context.instance( (with optional whitespace before paren)
PATTERN = re.compile(r"\bzmq\.asyncio\.Context\.instance\s*\(")


def _all_protected_files() -> list[Path]:
    """Return every existing .py file under PROTECTED_DIRS."""
    return [
        p
        for d in PROTECTED_DIRS
        for p in Path(d).rglob("*.py")
        if p.is_file()
    ]


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs where a Context.instance() appears.

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
                f"[no_zmq_singleton_in_tests] {p}:{lineno}: "
                f"use Context() + try/finally: ctx.term() instead of Context.instance() "
                f"— {line.strip()[:60]}",
                file=sys.stderr,
            )
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
