"""Tests for kill-report template and write_kill_report function (plan 01-12 Task 1).

[[Economics kill-switch v0.5]]
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent.parent  # boros/
TEMPLATE_PATH = ROOT / "docs" / "kill-report-template.md"


def test_template_exists() -> None:
    """kill-report-template.md must exist."""
    assert TEMPLATE_PATH.exists(), f"Missing: {TEMPLATE_PATH}"


def test_template_has_required_fields() -> None:
    """Template must contain all required placeholder fields."""
    content = TEMPLATE_PATH.read_text()
    required = [
        "{timestamp_iso}",
        "{git_sha}",
        "{run_id}",
        "{rows}",
        "{threshold",
        "{knob_tree_json}",
    ]
    for field in required:
        assert field in content, f"Template missing field: {field}"


def test_template_has_halt_semantics() -> None:
    """Template must explain halt semantics clearly."""
    content = TEMPLATE_PATH.read_text()
    assert "HALT" in content
    assert "R_apr_on_collateral" in content or "r_apr_on_collateral" in content.lower() or "R_apr" in content


def test_write_kill_report_creates_file(tmp_path: Path) -> None:
    """write_kill_report creates docs/kill-report-YYYYMMDD.md with per-market table."""
    from boros_brain.config.loader import load_config
    from boros_brain.screener.kill_report import write_kill_report

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "kill-report-template.md").write_text(TEMPLATE_PATH.read_text())

    config = load_config(ROOT / "strategy" / "v0.5-default.yaml")
    rows = [
        {
            "market_id": "BINANCE-ETHUSDT-29MAY2026",
            "r_apr_on_collateral": 0.04,
            "alt_yield_used": 0.05,
            "fill_loss_used": 0.02,
            "threshold": 0.07,
            "delta": -0.03,
            "halt_reason": "R_apr 0.0400 < threshold 0.0700",
        }
    ]

    # Patch git to avoid actual git call in test
    with patch("subprocess.check_output", return_value=b"deadbeef\n"):
        out_path = write_kill_report(rows, config=config, threshold=0.07)

    try:
        assert out_path.exists(), f"Kill-report not written: {out_path}"
        content = out_path.read_text()
        assert "BINANCE-ETHUSDT-29MAY2026" in content
        assert "0.0400" in content
        assert "0.0700" in content
        assert "-0.0300" in content
    finally:
        os.chdir(orig_cwd)


def test_write_kill_report_contains_knob_tree(tmp_path: Path) -> None:
    """Kill-report must contain the full knob tree JSON."""
    from boros_brain.config.loader import load_config
    from boros_brain.screener.kill_report import write_kill_report

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "kill-report-template.md").write_text(TEMPLATE_PATH.read_text())

    config = load_config(ROOT / "strategy" / "v0.5-default.yaml")
    rows = [
        {
            "market_id": "BINANCE-ETHUSDT-29MAY2026",
            "r_apr_on_collateral": 0.04,
            "alt_yield_used": 0.05,
            "fill_loss_used": 0.02,
            "threshold": 0.07,
            "delta": -0.03,
            "halt_reason": "R_apr 0.0400 < threshold 0.0700",
        }
    ]

    with patch("subprocess.check_output", return_value=b"deadbeef\n"):
        out_path = write_kill_report(rows, config=config, threshold=0.07)

    try:
        content = out_path.read_text()
        # The knob tree JSON should contain screener.alt_yield
        assert "alt_yield" in content, "Knob tree missing alt_yield"
        assert "fill_loss_coarse_bound" in content, "Knob tree missing fill_loss_coarse_bound"
    finally:
        os.chdir(orig_cwd)
