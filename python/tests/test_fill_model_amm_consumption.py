"""FILL-04 AMM consumption tests (Plan 02-02).

Tests for T-02-A-01 (non-negative amm_share) and T-02-A-02 (epoch conservation).
"""
from __future__ import annotations

import polars as pl
import pytest
from hypothesis import given, strategies as st

from boros_brain.fill_model.amm_consumption import (
    AMMConsumptionIdentityError,
    assert_epoch_conservation,
    compute_amm_share_timeseries,
)


def _make_balanced_epoch(combined_at_tick: float = 100.0, raw_at_tick: float = 60.0) -> tuple[pl.DataFrame, pl.DataFrame]:
    raw = pl.DataFrame({"snapshot_ts": [100, 200], "tick": [0, 0], "size": [raw_at_tick, raw_at_tick]})
    combined = pl.DataFrame({"snapshot_ts": [100, 200], "tick": [0, 0], "size_combined": [combined_at_tick, combined_at_tick]})
    return raw, combined


def test_amm_share_non_negative_basic() -> None:
    """T-02-A-01 — happy path: amm_share = combined - raw >= 0 everywhere."""
    raw, combined = _make_balanced_epoch()
    out = compute_amm_share_timeseries(raw, combined, epoch_start_ts=0, epoch_end_ts=1000)
    assert (out["amm_share"] >= 0.0).all(), "amm_share contains negative entries"
    assert out["amm_share"].sum() == pytest.approx(80.0)  # 2 snapshots × (100 - 60)


@given(
    combined_at=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    raw_at=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
)
def test_amm_share_non_negative(combined_at: float, raw_at: float) -> None:
    """T-02-A-01 — property: for combined >= raw, amm_share in output is always >= 0."""
    # Only valid inputs (combined >= raw) — invalid inputs are tested separately
    if combined_at < raw_at:
        return
    raw = pl.DataFrame({"snapshot_ts": [100], "tick": [0], "size": [raw_at]})
    combined = pl.DataFrame({"snapshot_ts": [100], "tick": [0], "size_combined": [combined_at]})
    out = compute_amm_share_timeseries(raw, combined, epoch_start_ts=0, epoch_end_ts=1000)
    assert (out["amm_share"] >= 0.0).all()


def test_amm_share_raises_on_combined_less_than_raw() -> None:
    """Combined < raw beyond tolerance = AMMConsumptionIdentityError with offending rows."""
    raw = pl.DataFrame({"snapshot_ts": [100], "tick": [0], "size": [100.0]})
    combined = pl.DataFrame({"snapshot_ts": [100], "tick": [0], "size_combined": [60.0]})
    with pytest.raises(AMMConsumptionIdentityError, match="combined < raw"):
        compute_amm_share_timeseries(raw, combined, epoch_start_ts=0, epoch_end_ts=1000)


def test_epoch_conservation_balanced() -> None:
    """T-02-A-02 — balanced epoch: assert returns None without raising."""
    # book_ahead_end = book_ahead_start - taker - amm + net_placements
    # 50 = 100 - 30 - 20 + 0
    assert_epoch_conservation(
        book_ahead_start=100.0,
        book_ahead_end=50.0,
        taker_consumption_ahead=30.0,
        amm_consumption=20.0,
        net_placements_ahead=0.0,
        epoch_start_ts=0,
        epoch_end_ts=100,
    )


def test_epoch_conservation_raises_on_imbalance() -> None:
    """T-02-A-02 — imbalanced epoch: raises AMMConsumptionIdentityError with delta in message."""
    with pytest.raises(AMMConsumptionIdentityError, match="delta="):
        assert_epoch_conservation(
            book_ahead_start=100.0,
            book_ahead_end=50.0,
            taker_consumption_ahead=10.0,  # should be 30 for balance
            amm_consumption=20.0,
            net_placements_ahead=0.0,
            epoch_start_ts=0,
            epoch_end_ts=100,
        )
