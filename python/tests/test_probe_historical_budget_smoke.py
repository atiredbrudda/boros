"""Smoke test for scripts/probe_historical_budget.py (A6 spike).

Only tests the --dry-run path, which skips all RPC calls.
Real reconstruction is a one-shot operator command, not run in CI.

Cases:
1. test_script_is_importable
   The script can be imported without errors.

2. test_dry_run_writes_verdict
   Running with --dry-run writes var/reports/a6_historical_budget_verdict.json
   with the expected fields (feasible, events_found, blockers, time_spent_hours).

3. test_dry_run_verdict_has_expected_fields
   The written JSON has all required fields.

4. test_dry_run_exit_code_zero
   The script exits 0 when run in --dry-run mode.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "probe_historical_budget.py"
VERDICT_PATH = ROOT / "var" / "reports" / "a6_historical_budget_verdict.json"

REQUIRED_VERDICT_FIELDS = {"feasible", "events_found", "blockers", "time_spent_hours"}


def test_script_is_importable() -> None:
    """The spike script can be imported (no syntax errors, clean imports)."""
    spec = importlib.util.spec_from_file_location("probe_historical_budget", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert hasattr(module, "main"), "Script must define a main() function"


def test_dry_run_writes_verdict(tmp_path: Path) -> None:
    """--dry-run must write var/reports/a6_historical_budget_verdict.json."""
    # Run from the repo root so the script writes to var/reports/ relative to it.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"Script exited {result.returncode}. stderr={result.stderr!r}"
    assert VERDICT_PATH.exists(), f"Verdict file not written at {VERDICT_PATH}"


def test_dry_run_verdict_has_expected_fields() -> None:
    """Written verdict JSON must contain all required fields."""
    # Ensure it exists (run dry-run if not)
    if not VERDICT_PATH.exists():
        subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=str(ROOT),
            check=True,
        )
    verdict = json.loads(VERDICT_PATH.read_text())
    missing = REQUIRED_VERDICT_FIELDS - set(verdict.keys())
    assert not missing, f"Verdict missing fields: {missing}"
    assert isinstance(verdict["feasible"], bool)
    assert isinstance(verdict["events_found"], list)
    assert isinstance(verdict["blockers"], list)
    assert isinstance(verdict["time_spent_hours"], float)


def test_dry_run_exit_code_zero() -> None:
    """--dry-run mode must exit 0 (infeasible is the expected outcome, not an error)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"Expected exit 0. returncode={result.returncode} stderr={result.stderr!r}"
