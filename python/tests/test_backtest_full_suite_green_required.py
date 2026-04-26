"""BACK-07 #6 — smoke test: full pytest collection succeeds with no errors.

Test functions:
  - test_full_pytest_suite_collects_green: uv run pytest --co exits 0 with no errors

This is a smoke test — NO importorskip. It verifies collection always succeeds.
Turns GREEN immediately (Wave 0) and stays green through all phases.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig  # noqa: E402 — no importorskip needed


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"

PYTHON_DIR = Path(__file__).resolve().parents[1]


def test_full_pytest_suite_collects_green() -> None:
    """BACK-07 success criterion #6: full pytest collection succeeds with exit code 0.

    Invokes `uv run pytest -q --co tests/` against the python/ directory
    and asserts collection exit code 0 with no ERROR lines.
    This ensures all test files (including RED-scaffolded backtest tests) can
    be collected cleanly regardless of which Wave has landed.
    """
    result = subprocess.run(
        ["uv", "run", "pytest", "-q", "--co", "tests/"],
        cwd=PYTHON_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = result.stdout + result.stderr
    error_lines = [line for line in combined.splitlines() if "ERROR" in line and "tests/" in line]

    assert result.returncode == 0, (
        f"pytest collection failed with exit code {result.returncode}.\n"
        f"ERROR lines:\n" + "\n".join(error_lines[:10]) + "\n"
        f"Full output:\n{combined[:2000]}"
    )
    assert not error_lines, (
        f"Collection errors found:\n" + "\n".join(error_lines)
    )
