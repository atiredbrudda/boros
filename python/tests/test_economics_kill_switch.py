"""Tests for DATA-09 economics kill-switch (plan 01-12 Task 1).

Tests the economics gate formula, fail-loud config validation, and halt behavior.
All 8 test cases per plan <behavior> block.

[[Economics kill-switch v0.5]]
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent  # boros/
FIXTURES = Path(__file__).parent / "fixtures"
STRATEGY_YAML = ROOT / "strategy" / "v0.5-default.yaml"


def test_formula_matches_research() -> None:
    """Test 1: formula correctness — PENDLE-units per 01-RESEARCH.md §Pattern 10.

    Given:
      e_liq_per_epoch=10, long_budget_share=0.8, Q_me=100, Σ_others=400, t_frac=1.0,
      required_collateral_pendle=20
    Expected:
      R_share_per_epoch_pendle = 10 * 0.8 * (100 / (400 + 100)) = 1.6
      R_apr_pendle = 1.6 * 52 / 20 = 4.16
    """
    from boros_brain.screener.economics_gate import compute_r_apr_on_collateral_pendle

    result = compute_r_apr_on_collateral_pendle(
        e_liq_per_epoch=10.0,
        side_split=0.8,
        q_me=100.0,
        sigma_others=400.0,
        t_frac=1.0,
        required_collateral_pendle=20.0,
    )
    assert abs(result - 4.16) < 1e-6, f"Expected 4.16, got {result}"


def test_pass_case(tmp_path: Path) -> None:
    """Test 2: market with R_apr=0.15 > threshold 0.07 stays in shortlist."""
    from boros_brain.screener.economics_gate import run_economics_gate

    metrics_path = tmp_path / "screener_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "market_id": "MARKET-PASS",
                        "r_apr_potential": 0.15,
                        "filter_pass": True,
                    }
                ],
                "shortlist": ["MARKET-PASS"],
            }
        )
    )

    # Patch docs dir to avoid writing kill-report to project root
    with patch("boros_brain.screener.economics_gate.Path") as mock_path_cls:
        # Allow reads/writes to work normally, but redirect docs/kill-report writes
        mock_path_cls.side_effect = Path
        shortlist = run_economics_gate(str(STRATEGY_YAML), str(metrics_path))

    assert "MARKET-PASS" in shortlist


def test_drop_case(tmp_path: Path) -> None:
    """Test 3: market with R_apr=0.06 < threshold 0.07 is dropped."""
    from boros_brain.screener.economics_gate import run_economics_gate

    metrics_path = tmp_path / "screener_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "market_id": "MARKET-PASSING-DATA08",
                        "r_apr_potential": 0.06,
                        "filter_pass": True,
                    }
                ],
                "shortlist": ["MARKET-PASSING-DATA08"],
            }
        )
    )

    from boros_brain.screener.economics_gate import ProjectHalt

    with pytest.raises(ProjectHalt):
        # R_apr=0.06 < 0.07 → empty shortlist → halt
        run_economics_gate(str(STRATEGY_YAML), str(metrics_path))


def test_empty_shortlist_halt(tmp_path: Path) -> None:
    """Test 4: all-fail fixture → ProjectHalt raised + kill-report written."""
    from boros_brain.screener.economics_gate import ProjectHalt, run_economics_gate

    # Redirect var/reports to tmp_path
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "var" / "reports").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    # Copy kill-report template
    template_src = ROOT / "docs" / "kill-report-template.md"
    if template_src.exists():
        (tmp_path / "docs" / "kill-report-template.md").write_text(template_src.read_text())
    try:
        with pytest.raises(ProjectHalt):
            run_economics_gate(
                str(STRATEGY_YAML),
                str(FIXTURES / "screener_metrics_all_fail.json"),
            )
        # kill-report must have been written (exclude template itself)
        kill_reports = [p for p in (tmp_path / "docs").glob("kill-report-*.md") if p.name != "kill-report-template.md"]
        assert len(kill_reports) >= 1, "Expected kill-report to be written"
    finally:
        os.chdir(orig_cwd)


def test_fail_loud_missing_knob(tmp_path: Path) -> None:
    """Test 5: fixture with alt_yield missing → ConfigError exit 2 behavior."""
    from boros_brain.screener.economics_gate import ConfigError, run_economics_gate

    metrics_path = tmp_path / "screener_metrics.json"
    metrics_path.write_text(json.dumps({"results": [], "shortlist": []}))

    config_path = FIXTURES / "config_missing_alt_yield.yaml"

    with pytest.raises(ConfigError) as exc_info:
        run_economics_gate(str(config_path), str(metrics_path))

    assert "alt_yield missing" in str(
        exc_info.value
    ), f"Expected 'alt_yield missing' in error message, got: {exc_info.value}"


def test_fail_loud_unit_confusion(tmp_path: Path) -> None:
    """Test 6: alt_yield=5.0 (500%) → ConfigError 'out of range'."""
    from boros_brain.screener.economics_gate import ConfigError, run_economics_gate

    metrics_path = tmp_path / "screener_metrics.json"
    metrics_path.write_text(json.dumps({"results": [], "shortlist": []}))

    config_path = FIXTURES / "config_alt_yield_unit_confusion.yaml"

    with pytest.raises(ConfigError) as exc_info:
        run_economics_gate(str(config_path), str(metrics_path))

    assert "out of range" in str(exc_info.value), f"Expected 'out of range' in error message, got: {exc_info.value}"
    assert "alt_yield" in str(exc_info.value)


def test_kill_report_contents(tmp_path: Path) -> None:
    """Test 7: kill-report contains ISO8601 timestamp, market table, knob tree."""
    from boros_brain.screener.economics_gate import ProjectHalt, run_economics_gate

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "var" / "reports").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    # Copy template
    template_src = ROOT / "docs" / "kill-report-template.md"
    if template_src.exists():
        (tmp_path / "docs" / "kill-report-template.md").write_text(template_src.read_text())
    try:
        with pytest.raises(ProjectHalt):
            run_economics_gate(
                str(STRATEGY_YAML),
                str(FIXTURES / "screener_metrics_all_fail.json"),
            )
        # Exclude kill-report-template.md (glob matches it too — template is not a report)
        kill_reports = [p for p in (tmp_path / "docs").glob("kill-report-*.md") if p.name != "kill-report-template.md"]
        assert len(kill_reports) >= 1
        content = kill_reports[0].read_text()
        # Must contain per-market row
        assert "BINANCE-ETHUSDT-29MAY2026" in content, "Market ID missing from kill-report"
        # Must contain threshold value
        assert "0.07" in content or "threshold" in content.lower(), "Threshold missing"
        # Must reference HALT decision
        assert "HALT" in content or "halt" in content.lower(), "HALT decision missing"
    finally:
        os.chdir(orig_cwd)


def test_mixed_shortlist_exits_0(tmp_path: Path) -> None:
    """Test 8: mixed fixture (1 pass + 2 fail) → shortlist has 1 market, no kill-report."""
    from boros_brain.screener.economics_gate import run_economics_gate

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "var" / "reports").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    # Copy template (won't be needed, but must exist if write_kill_report called)
    template_src = ROOT / "docs" / "kill-report-template.md"
    if template_src.exists():
        (tmp_path / "docs" / "kill-report-template.md").write_text(template_src.read_text())
    try:
        shortlist = run_economics_gate(
            str(STRATEGY_YAML),
            str(FIXTURES / "screener_metrics_mixed.json"),
        )
        assert shortlist == ["BINANCE-ETHUSDT-29MAY2026"], f"Expected only the passing market, got: {shortlist}"
        # No kill-report should have been written (exclude template itself)
        kill_reports = [p for p in (tmp_path / "docs").glob("kill-report-*.md") if p.name != "kill-report-template.md"]
        assert len(kill_reports) == 0, "Kill-report should NOT be written for non-empty shortlist"
    finally:
        os.chdir(orig_cwd)


def test_epochs_per_year_constant() -> None:
    """Acceptance criteria: EPOCHS_PER_YEAR = 52 locked constant."""
    from boros_brain.screener.economics_gate import EPOCHS_PER_YEAR

    assert EPOCHS_PER_YEAR == 52


def test_formula_r_share_computation() -> None:
    """Verify R_share_per_epoch_pendle × EPOCHS_PER_YEAR / required_collateral_pendle formula."""
    from boros_brain.screener.economics_gate import EPOCHS_PER_YEAR, compute_r_apr_on_collateral_pendle

    # Simple sanity: zero sigma_others means bot gets all of side_split
    result = compute_r_apr_on_collateral_pendle(
        e_liq_per_epoch=10.0,
        side_split=1.0,
        q_me=10.0,
        sigma_others=0.0,
        t_frac=1.0,
        required_collateral_pendle=10.0,
    )
    # R_share = 10 * 1.0 * (10/10) = 10; R_apr = 10 * 52 / 10 = 52.0
    expected = 10.0 * 1.0 * (10.0 / (0.0 + 10.0)) * EPOCHS_PER_YEAR / 10.0
    assert abs(result - expected) < 1e-9
