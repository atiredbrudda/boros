"""DECIDE-04 — no_threshold_dials_lint.py audit script tests.

Covers:
  - test_audit_passes_on_main: lint passes on whole codebase (xfail until 04-03)
  - test_audit_catches_threshold_field: lint detects `cancel_threshold: float = 0.5`

DECIDE-04 invariant: only EV-input model parameters and breaker thresholds
(under decision.breakers.*) may be tunable. Generic `_threshold` / `_dial` /
`_cutoff` identifiers anywhere else under decision/ are a regression.

See scripts/no_threshold_dials_lint.py — skeleton lands in Plan 04-01;
regex + ALLOWED_FILES tightened in Plan 04-03. [[ev-cancel-rule]]
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# The lint script tests do NOT need importorskip — the script files are
# plain Python in scripts/ (no boros_brain import required to collect).


def _load_lint_module():
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    lint_script = scripts_dir / "no_threshold_dials_lint.py"
    assert lint_script.exists(), f"Lint script not found at {lint_script}"
    spec = importlib.util.spec_from_file_location("no_threshold_dials_lint", lint_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.xfail(reason="DECIDE-04 lint regex tightened in 04-03; decision/config.py does not exist yet")
def test_audit_passes_on_main() -> None:
    """DECIDE-04 — lint passes on the full codebase when no rogue threshold dials exist.

    xfail until 04-03 creates decision/config.py with properly-scoped BreakerConfig
    sub-models. Until then the protected dir may not exist or may have interim files
    that trigger the linter.

    Turns PASS in Plan 04-03 once ALLOWED_FILES is configured correctly.
    """
    mod = _load_lint_module()
    exit_code = mod.main()
    assert exit_code == 0


def test_audit_catches_threshold_field(tmp_path: Path) -> None:
    """DECIDE-04 — lint detects `cancel_threshold: float = 0.5` in decision/.

    Writes an offending file with a plain `_threshold` field name outside the
    BreakerConfig family then asserts lint exit code == 1.
    """
    mod = _load_lint_module()

    # Write offending file into the protected directory
    protected_dir = (
        Path(__file__).resolve().parents[2]
        / "python" / "src" / "boros_brain" / "decision"
    )
    protected_dir.mkdir(parents=True, exist_ok=True)
    bad_file = protected_dir / "_test_lint_probe_threshold.py"
    try:
        bad_file.write_text(
            "class BadConfig:\n    cancel_threshold: float = 0.5\n"
        )
        exit_code = mod.main()
        assert exit_code == 1, (
            f"Expected lint exit code 1 (threshold dial violation), got {exit_code}"
        )
    finally:
        bad_file.unlink(missing_ok=True)
