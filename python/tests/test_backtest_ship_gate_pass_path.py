"""BACK-07 — ship-gate pass path: always-positive P&L passes and writes report.

Test functions:
  - test_synthetic_positive_pnl_passes: always-positive daily_pnl → passed=True AND ship-gate-report.md written

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


def test_synthetic_positive_pnl_passes(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-07: always-positive daily_pnl passes ship gate AND ship-gate-report.md is written.

    Uses a synthetic daily_pnl array where every value >> threshold.
    Expects ShipGateVerdict.passed=True and the report file to exist.
    """
    import numpy as np
    from boros_brain.manifest.writer import build_run_manifest

    manifest = build_run_manifest(default_config, parent_run_id=None)

    # Always-positive scenario: P&L = 0.5 APR daily (>> alt_yield threshold)
    daily_pnl = np.array([0.5 / 365] * 90)

    verdict = evaluate_ship_gate(daily_pnl, manifest=manifest, config=default_config)
    assert verdict.passed is True, (
        f"Expected passed=True for always-positive P&L, got {verdict.passed}. "
        f"P5 bootstrap: {getattr(verdict, 'p5_annualized', '?')}, "
        f"threshold: {getattr(verdict, 'threshold', '?')}"
    )

    report_path = write_ship_gate_report(
        verdict, config=default_config, manifest=manifest, output_dir=tmp_path
    )
    assert report_path.exists(), f"ship-gate-report.md was not written to {report_path}"
    assert report_path.name.endswith(".md"), f"Expected .md report, got {report_path.name}"
