"""BACK-08 — perturbation sign flip detection.

Test functions:
  - test_known_fragile_knob_flagged: p_purge perturbed -20% flips P&L sign → fragile=True
  - test_non_fragile_knob_not_flagged: stable knob perturbed → fragile=False
  - test_fragile_does_not_auto_fail_ship_gate: fragile knob + 5th-pct above threshold → passed=True with fragility flag

Turns GREEN in Plan 05-08 when boros_brain.backtest.sweeps.perturbation lands.

[[backtest-perturbation-grid-pydantic-reflection]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-08.
perturbation_mod = pytest.importorskip("boros_brain.backtest.sweeps.perturbation")
detect_sign_flip = perturbation_mod.detect_sign_flip

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_known_fragile_knob_flagged() -> None:
    """BACK-08: detect_sign_flip returns True when P&L sign flips under perturbation.

    Scenario: unperturbed_pnl > 0, but low_pnl < 0 (knob perturbed -20%) → fragile=True.
    """
    # Unperturbed: positive P&L; low (−20% perturbation): negative P&L
    assert detect_sign_flip(
        unperturbed_pnl=0.05,
        low_pnl=-0.03,
        high_pnl=0.07,
    ) is True


def test_non_fragile_knob_not_flagged() -> None:
    """BACK-08: detect_sign_flip returns False when P&L sign is consistent under perturbation."""
    # Both low and high perturbations stay positive
    assert detect_sign_flip(
        unperturbed_pnl=0.05,
        low_pnl=0.03,
        high_pnl=0.07,
    ) is False


def test_fragile_does_not_auto_fail_ship_gate(default_config: BotConfig) -> None:
    """BACK-08: a fragile knob does NOT automatically fail the ship gate.

    If the 5th-percentile bootstrap P&L is above the threshold, passed=True
    even when some knobs are flagged as fragile. Fragility is a warning flag,
    not a hard kill condition.
    """
    pytest.skip("Plan 05-08 implements this — currently RED")
