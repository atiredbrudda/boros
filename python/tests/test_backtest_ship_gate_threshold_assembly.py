"""BACK-07 — ship-gate threshold assembly: alt_yield + all_fees.

Test functions:
  - test_threshold_equals_alt_yield_plus_all_fees: assemble_threshold(config).total == alt_yield + all_fees_threshold
  - test_components_breakdown_persisted: ThresholdComponents.components dict has alt_yield + all_fees keys
  - test_mutation_shifts_threshold: bumping all_fees_threshold by Δ shifts threshold by exactly Δ

Turns GREEN in Plan 05-07 when boros_brain.backtest.ship_gate lands.

[[backtest-ship-gate-threshold-assembly]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-07.
ship_gate_mod = pytest.importorskip("boros_brain.backtest.ship_gate")
assemble_threshold = ship_gate_mod.assemble_threshold
ThresholdComponents = ship_gate_mod.ThresholdComponents

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_threshold_equals_alt_yield_plus_all_fees(default_config: BotConfig) -> None:
    """BACK-07: threshold.total == screener.alt_yield + backtest.all_fees_threshold."""
    tc = assemble_threshold(default_config)
    expected = default_config.screener.alt_yield + default_config.backtest.all_fees_threshold
    assert tc.total == pytest.approx(expected), (
        f"threshold.total={tc.total} != alt_yield({default_config.screener.alt_yield}) "
        f"+ all_fees({default_config.backtest.all_fees_threshold}) = {expected}"
    )


def test_components_breakdown_persisted(default_config: BotConfig) -> None:
    """BACK-07: ThresholdComponents.components dict contains 'alt_yield' and 'all_fees' keys."""
    tc = assemble_threshold(default_config)
    assert hasattr(tc, "components"), "ThresholdComponents must have a .components dict"
    assert "alt_yield" in tc.components, "components must include 'alt_yield' key"
    assert "all_fees" in tc.components, "components must include 'all_fees' key"


def test_mutation_shifts_threshold(default_config: BotConfig) -> None:
    """BACK-07: bumping all_fees_threshold by Δ shifts threshold.total by exactly Δ."""
    tc_base = assemble_threshold(default_config)

    delta = 0.005
    new_backtest = default_config.backtest.model_copy(
        update={"all_fees_threshold": default_config.backtest.all_fees_threshold + delta}
    )
    config_bumped = default_config.model_copy(update={"backtest": new_backtest})
    tc_bumped = assemble_threshold(config_bumped)

    assert tc_bumped.total == pytest.approx(tc_base.total + delta, abs=1e-9), (
        f"Bumping all_fees_threshold by {delta} should shift threshold by exactly {delta}. "
        f"Got: {tc_bumped.total:.6f} (base was {tc_base.total:.6f})"
    )
