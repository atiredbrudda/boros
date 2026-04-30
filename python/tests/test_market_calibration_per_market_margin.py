"""Tests for Phase 05.2 Wave 1 per-market margin fields added to MarketCalibration.

Test IDs:
- T-05.2-W1-MC-01: MarketCalibration accepts all three new per-market fields
- T-05.2-W1-MC-02: MarketCalibration accepts None for margin_per_yu_usd (backward compat)
- T-05.2-W1-MC-03: MarketCalibration rejects margin_per_yu_usd < 0.01 (ge=0.01)
- T-05.2-W1-MC-04: MarketCalibration rejects daily_volatility_pct > 100.0 (le=100.0)
- T-05.2-W1-MC-05: MarketCalibration rejects liquidation_buffer_safety_n < 1 (ge=1)

These tests verify that the three new Optional/defaulted fields in MarketCalibration
(margin_per_yu_usd, daily_volatility_pct, liquidation_buffer_safety_n) have correct
Pydantic bounds and backward-compat defaults.

See [[phase-05-2-margin-per-yu-rename]] for the rename narrative.
"""

from __future__ import annotations

import pytest
import pydantic

from boros_brain.config.schema import MarketCalibration


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _base_kwargs() -> dict:
    """Minimal valid MarketCalibration kwargs (no new fields)."""
    return dict(
        market_id="BINANCE-ETHUSDT-25SEP2026",
        scale=606985714285.0,
        s=0.0,
        clo_lower_thresh=9300.0,
        clo_upper_thresh=9500.0,
        fIndex_oracle_address="0x0000000000000000000000000000000000000000",
        maturity_ts=1790294400,
        underlying_exchange="binance",
        underlying_symbol="ETHUSDT",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_market_calibration_accepts_per_market_margin() -> None:
    """T-05.2-W1-MC-01 — All three new fields accepted with valid values."""
    calib = MarketCalibration(
        **_base_kwargs(),
        margin_per_yu_usd=18.30,
        daily_volatility_pct=0.34,
        liquidation_buffer_safety_n=3,
    )
    assert calib.margin_per_yu_usd == pytest.approx(18.30)
    assert calib.daily_volatility_pct == pytest.approx(0.34)
    assert calib.liquidation_buffer_safety_n == 3


def test_market_calibration_accepts_none_margin() -> None:
    """T-05.2-W1-MC-02 — margin_per_yu_usd=None (backward compat default)."""
    calib = MarketCalibration(**_base_kwargs(), margin_per_yu_usd=None)
    assert calib.margin_per_yu_usd is None
    # Other new fields also default correctly.
    assert calib.daily_volatility_pct is None
    assert calib.liquidation_buffer_safety_n == 3  # default


def test_market_calibration_rejects_negative_margin() -> None:
    """T-05.2-W1-MC-03 — margin_per_yu_usd=-1.0 rejected (ge=0.01)."""
    with pytest.raises(pydantic.ValidationError):
        MarketCalibration(**_base_kwargs(), margin_per_yu_usd=-1.0)


def test_market_calibration_rejects_volatility_over_100() -> None:
    """T-05.2-W1-MC-04 — daily_volatility_pct=200.0 rejected (le=100.0)."""
    with pytest.raises(pydantic.ValidationError):
        MarketCalibration(**_base_kwargs(), daily_volatility_pct=200.0)


def test_market_calibration_rejects_zero_buffer_n() -> None:
    """T-05.2-W1-MC-05 — liquidation_buffer_safety_n=0 rejected (ge=1)."""
    with pytest.raises(pydantic.ValidationError):
        MarketCalibration(**_base_kwargs(), liquidation_buffer_safety_n=0)
