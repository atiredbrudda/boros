"""Tests for DATA-10 daily re-screen scheduler (plan 01-12 Task 2).

6 test cases per plan <behavior> block.

[[Daily re-screen scheduler]]
[[Economics kill-switch v0.5]]
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent  # boros/
FIXTURES = Path(__file__).parent / "fixtures"
STRATEGY_YAML = ROOT / "strategy" / "v0.5-default.yaml"
PLIST_PATH = ROOT / "scripts" / "launchd" / "com.boros.rescreen.plist"


def test_full_chain_invocation_order() -> None:
    """Test 1: run_daily_rescreen invokes ingest -> screener -> economics gate in order."""
    from boros_brain.screener.rescreen import run_daily_rescreen

    call_order: list[str] = []

    mock_ingest = MagicMock(side_effect=lambda *a, **kw: call_order.append("ingest"))
    mock_screener = MagicMock(side_effect=lambda *a, **kw: call_order.append("screener"))
    mock_gate = MagicMock(side_effect=lambda *a, **kw: (call_order.append("gate"), ["MKT"])[1])

    with (
        patch("boros_brain.screener.rescreen._run_ingest_stage", mock_ingest),
        patch("boros_brain.screener.rescreen._run_screener_stage", mock_screener),
        patch("boros_brain.screener.rescreen._run_gate_stage", mock_gate),
        patch("boros_brain.screener.rescreen.Path") as mock_path,
    ):
        # Make yesterday_path.exists() return False (no previous shortlist)
        mock_path_inst = MagicMock()
        mock_path_inst.exists.return_value = False
        mock_path.side_effect = Path
        mock_path.return_value = mock_path_inst

        # Intercept the rescreen_diff write
        with (
            patch("boros_brain.screener.rescreen._write_rescreen_diff"),
            patch("boros_brain.screener.rescreen._load_yesterday_shortlist", return_value=set()),
        ):
            run_daily_rescreen(str(STRATEGY_YAML))

    assert call_order == ["ingest", "screener", "gate"], f"Expected ingest->screener->gate order, got: {call_order}"


def test_new_entrant_flag(tmp_path: Path) -> None:
    """Test 2: yesterday=[ETH, BTC], today=[ETH, BTC, SOL] -> new_entrants=[SOL]."""
    from boros_brain.screener.rescreen import _write_rescreen_diff

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "var" / "reports").mkdir(parents=True)

    try:
        yesterday = {"BINANCE-ETHUSDT-29MAY2026", "BINANCE-BTCUSDT-29MAY2026"}
        today = {"BINANCE-ETHUSDT-29MAY2026", "BINANCE-BTCUSDT-29MAY2026", "HYPERLIQUID-SOLUSDT-29MAY2026"}

        _write_rescreen_diff(yesterday, today)

        diff = json.loads((tmp_path / "var" / "reports" / "rescreen_diff.json").read_text())
        assert diff["new_entrants"] == ["HYPERLIQUID-SOLUSDT-29MAY2026"]
        assert diff["dropped"] == []
        assert set(diff["unchanged"]) == {"BINANCE-ETHUSDT-29MAY2026", "BINANCE-BTCUSDT-29MAY2026"}
    finally:
        os.chdir(orig_cwd)


def test_dropped_flag(tmp_path: Path) -> None:
    """Test 3: yesterday=[ETH, BTC], today=[ETH] -> dropped=[BTC], warning logged."""
    from boros_brain.screener.rescreen import _write_rescreen_diff

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "var" / "reports").mkdir(parents=True)

    try:
        yesterday = {"BINANCE-ETHUSDT-29MAY2026", "BINANCE-BTCUSDT-29MAY2026"}
        today = {"BINANCE-ETHUSDT-29MAY2026"}

        with patch("boros_brain.screener.rescreen.log") as mock_log:
            _write_rescreen_diff(yesterday, today)
            # Verify structured WARNING log emitted for dropped market
            mock_log.warning.assert_called_once_with(
                "rescreen.market_dropped",
                market_id="BINANCE-BTCUSDT-29MAY2026",
            )

        diff = json.loads((tmp_path / "var" / "reports" / "rescreen_diff.json").read_text())
        assert diff["dropped"] == ["BINANCE-BTCUSDT-29MAY2026"]
        assert diff["new_entrants"] == []
        assert diff["unchanged"] == ["BINANCE-ETHUSDT-29MAY2026"]
    finally:
        os.chdir(orig_cwd)


def test_halt_propagation(tmp_path: Path) -> None:
    """Test 4: economics gate raises ProjectHalt -> propagated + diff written with dropped markets."""
    from boros_brain.screener.economics_gate import ProjectHalt
    from boros_brain.screener.rescreen import run_daily_rescreen

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "var" / "reports").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    # Copy kill-report template for the halt writer
    template_src = ROOT / "docs" / "kill-report-template.md"
    if template_src.exists():
        (tmp_path / "docs" / "kill-report-template.md").write_text(template_src.read_text())

    try:
        with (
            patch("boros_brain.screener.rescreen._run_ingest_stage"),
            patch("boros_brain.screener.rescreen._run_screener_stage"),
            patch("boros_brain.screener.rescreen._run_gate_stage", side_effect=ProjectHalt("empty shortlist")),
            patch(
                "boros_brain.screener.rescreen._load_yesterday_shortlist",
                return_value={"BINANCE-ETHUSDT-29MAY2026"},
            ),
            pytest.raises(ProjectHalt),
        ):
            run_daily_rescreen(str(STRATEGY_YAML))

        # rescreen_diff.json should be written even on halt
        diff_path = tmp_path / "var" / "reports" / "rescreen_diff.json"
        assert diff_path.exists(), "rescreen_diff.json should be written on halt"
        diff = json.loads(diff_path.read_text())
        # Yesterday had ETH, today has nothing -> ETH was dropped
        assert "BINANCE-ETHUSDT-29MAY2026" in diff["dropped"]
    finally:
        os.chdir(orig_cwd)


def test_launchd_plist_valid_xml() -> None:
    """Test 5: com.boros.rescreen.plist validates as valid XML plist with correct schedule."""
    assert PLIST_PATH.exists(), f"Plist not found: {PLIST_PATH}"

    # Validate with plutil
    result = subprocess.run(
        ["plutil", "-lint", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"plutil -lint failed: {result.stdout}\n{result.stderr}"

    content = PLIST_PATH.read_text()
    assert "StartCalendarInterval" in content, "Missing StartCalendarInterval"
    # Hour=3 for 03:00 UTC
    assert "<integer>3</integer>" in content, "Missing Hour=3 in CalendarInterval"
    # KeepAlive=false (one-shot daily job)
    assert "<false/>" in content, "Missing KeepAlive=false"
    # ProgramArguments invokes the rescreen module
    assert "boros_brain.screener.rescreen" in content, "Missing rescreen module in ProgramArguments"
    # Logs to supervisor dir
    assert "com.boros.rescreen" in content, "Missing com.boros.rescreen log reference"


def test_pitfalls_a5_docstring() -> None:
    """Test 6: run_daily_rescreen docstring references PITFALLS §A5 competition crowding."""
    import boros_brain.screener.rescreen as rescreen_mod

    docstring = rescreen_mod.__doc__ or ""
    fn_doc = rescreen_mod.run_daily_rescreen.__doc__ or ""
    combined = docstring + fn_doc

    assert (
        "A5" in combined or "Competition crowding" in combined or "competition" in combined.lower()
    ), "Expected PITFALLS §A5 / competition crowding reference in module or function docstring"
