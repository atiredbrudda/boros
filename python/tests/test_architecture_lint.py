"""T-02-L-01 — architecture.yml drift check (Plan 02-01).

Invokes scripts/architecture_lint.py as a subprocess so that every code commit
that modifies docs/architecture.yml is validated end-to-end in the test suite.

This is the PROTO-02 lint gate: architecture.yml must declare every module node,
public_function, and edge that exists in the source tree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_architecture_lint_clean() -> None:
    """T-02-L-01: architecture_lint.py exits 0 — no drift between code and architecture.yml."""
    result = subprocess.run(
        [sys.executable, "scripts/architecture_lint.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"architecture_lint.py reported drift:\n" f"stdout:\n{result.stdout}\n" f"stderr:\n{result.stderr}"
    )
