"""DECIDE-04 — no_threshold_dials_lint.py audit script tests.

Covers:
  - test_audit_passes_on_main: lint passes on whole codebase
  - test_audit_catches_threshold_field: lint detects `cancel_threshold: float = 0.5`

DECIDE-04 invariant: only EV-input model parameters and breaker thresholds
(under decision.breakers.*) may be tunable. Generic `_threshold` / `_dial` /
`_cutoff` identifiers anywhere else under decision/ are a regression.

See scripts/no_threshold_dials_lint.py — skeleton lands in Plan 04-01;
regex + ALLOWED_FILES tightened in Plan 04-03. [[ev-cancel-rule]]
See [[ev-cancel-rule-implementation-v05]] for the full EV equation.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

# The lint script tests do NOT need importorskip — the script files are
# plain Python in scripts/ (no boros_brain import required to collect).

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_lint_module(lint_script: Path):
    """Load the lint module fresh (avoids cached state from prior calls)."""
    spec = importlib.util.spec_from_file_location(lint_script.stem + "_fresh", lint_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_lint_script() -> Path:
    scripts_dir = REPO_ROOT / "scripts"
    lint_script = scripts_dir / "no_threshold_dials_lint.py"
    assert lint_script.exists(), f"Lint script not found at {lint_script}"
    return lint_script


def test_audit_passes_on_main() -> None:
    """DECIDE-04 — lint passes on the full codebase when no rogue threshold dials exist.

    decision/config.py is in ALLOWED_FILES and legitimately contains BreakerConfig
    sub-models with `_threshold` style field names. engine.py and gas_history.py
    contain no such names. The lint MUST exit 0 on a clean Phase-4-Wave-2A tree.
    """
    lint_script = _get_lint_script()
    old_cwd = os.getcwd()
    try:
        # Lint uses relative PROTECTED_DIRS — must run from repo root
        os.chdir(REPO_ROOT)
        mod = _load_lint_module(lint_script)
        exit_code = mod.main()
        assert exit_code == 0, f"no_threshold_dials_lint exited {exit_code} (expected 0 on a clean tree)"
    finally:
        os.chdir(old_cwd)


def test_audit_catches_threshold_field(tmp_path: Path) -> None:
    """DECIDE-04 — lint detects `cancel_threshold: float = 0.5` in decision/.

    Writes an offending file with a plain `_threshold` field name outside the
    BreakerConfig family then asserts lint exit code == 1.
    """
    lint_script = _get_lint_script()

    # Write offending file into the protected directory
    protected_dir = REPO_ROOT / "python" / "src" / "boros_brain" / "decision"
    protected_dir.mkdir(parents=True, exist_ok=True)
    bad_file = protected_dir / "_test_lint_probe_threshold.py"
    old_cwd = os.getcwd()
    try:
        bad_file.write_text("class BadConfig:\n    cancel_threshold: float = 0.5\n")
        # Lint uses relative PROTECTED_DIRS — must run from repo root
        os.chdir(REPO_ROOT)
        mod = _load_lint_module(lint_script)
        exit_code = mod.main()
        assert exit_code == 1, f"Expected lint exit code 1 (threshold dial violation), got {exit_code}"
    finally:
        os.chdir(old_cwd)
        bad_file.unlink(missing_ok=True)
