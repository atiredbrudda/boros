"""BACK-07 — ship-gate fail path: always-negative P&L fails and writes kill report.

Test functions:
  - test_synthetic_negative_pnl_fails_and_writes_kill_report: always-negative daily_pnl → passed=False AND kill-report.md written

Turns GREEN in Plan 05-07 when boros_brain.backtest.ship_gate lands.

[[backtest-ship-gate-threshold-assembly]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-07.
ship_gate_mod = pytest.importorskip("boros_brain.backtest.ship_gate")
evaluate_ship_gate = ship_gate_mod.evaluate_ship_gate
write_ship_gate_report = ship_gate_mod.write_ship_gate_report

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_synthetic_negative_pnl_fails_and_writes_kill_report(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-07: always-negative daily_pnl fails ship gate AND Markdown kill-report exists.

    Uses a synthetic daily_pnl array where every value is deeply negative.
    Expects ShipGateVerdict.passed=False and the kill-report file to be written.
    """
    import numpy as np
    from boros_brain.manifest.writer import build_run_manifest

    manifest = build_run_manifest(default_config, parent_run_id=None)

    # Always-negative scenario: P&L = -5% daily
    daily_pnl = np.array([-0.05] * 90)

    verdict = evaluate_ship_gate(daily_pnl, manifest=manifest, config=default_config)
    assert verdict.passed is False, (
        f"Expected passed=False for always-negative P&L, got {verdict.passed}. "
        f"P5 bootstrap: {getattr(verdict, 'p5_annualized', '?')}, "
        f"threshold: {getattr(verdict, 'threshold', '?')}"
    )

    report_path = write_ship_gate_report(
        verdict, config=default_config, manifest=manifest, output_dir=tmp_path
    )
    assert report_path.exists(), f"Kill report was not written to {report_path}"
    content = report_path.read_text()
    # Kill report must contain a kill/fail indication
    assert any(kw in content.lower() for kw in ("kill", "fail", "halt", "rejected")), (
        f"Kill report does not contain kill/fail language. Content: {content[:200]}"
    )
