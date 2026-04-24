"""Test: no_time_time_lint.py pre-commit hook behavior — plan 01-07 Task 1."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # boros/


def _run_lint() -> int:
    r = subprocess.run(
        ["python", str(ROOT / "scripts/no_time_time_lint.py")],
        cwd=str(ROOT),
        env={**os.environ, "CI": "true"},
    )
    return r.returncode


def test_lint_passes_on_clean_tree() -> None:
    """At plan-07 completion, the clean tree must pass the lint (exit 0)."""
    assert _run_lint() == 0


def test_lint_fails_on_injected_time_time_in_data() -> None:
    """A file with time.time() injected into brain/data/ must cause exit 1."""
    injected = ROOT / "python/src/boros_brain/data/_test_injected.py"
    try:
        injected.write_text("import time\ndef f(): return time.time()\n")
        # Run lint with the full-tree scan (no staged files, so falls back to tree walk)
        result = subprocess.run(
            ["python", str(ROOT / "scripts/no_time_time_lint.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Lint should have failed on injected time.time(), but exited 0.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
    finally:
        if injected.exists():
            injected.unlink()


def test_lint_ignores_time_time_in_tests() -> None:
    """Files under python/tests/ may use time.time() freely — lint must NOT fail."""
    test_with_time = ROOT / "python/tests/_test_time_time_allowed.py"
    try:
        test_with_time.write_text("import time\ndef t(): return time.time()\n")
        assert _run_lint() == 0, "Lint should ignore time.time() in test files"
    finally:
        if test_with_time.exists():
            test_with_time.unlink()
