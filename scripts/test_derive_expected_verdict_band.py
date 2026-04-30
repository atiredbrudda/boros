"""Smoke test for `scripts/derive_expected_verdict_band.py`.

Pinned-fixture round-trip: same inputs → identical output JSON to 1e-9 relative
tolerance. Catches drift in the formula or in the band-grid sweep.

Run::

    cd /Users/macbookair/boros/python && uv run pytest -xvs ../scripts/test_derive_expected_verdict_band.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.derive_expected_verdict_band import (  # noqa: E402
    BandInputs,
    compute_apr_usd_fraction,
    compute_share,
    derive_band,
)


def test_share_formula_q_me_5_sigma_165_reconciles_dapp_489_percent_badge() -> None:
    """[[dapp-apr-reconciliation-2026-04-30]] anchor: (q_me=5.0, sigma=165) → ~486% APR.

    This is the empirical reconciliation of the dapp's 489% LONG APR badge.
    Reproduces the badge to within ±1% (489 → 486.4 = 0.5% Δ).
    """
    apr = compute_apr_usd_fraction(
        q_me_yu=5.0,
        sigma_yu=165.0,
        side_split=0.760,
        e_liq_per_epoch_pendle=309.96,
        pendle_price_usd=1.35,
        collateral_usd=100.0,
    )
    assert math.isclose(apr, 4.864, rel_tol=2e-3), f"got {apr=}"
    # Cross-check: APR reconciles dapp's 489% headline within ±1%
    assert abs(apr - 4.89) / 4.89 < 0.01


def test_share_formula_q_me_4_92_sigma_75_reproduces_w5_overshoot() -> None:
    """CONTEXT.md's old "75 effective pool" assumption produces ~1019% APR — explains W5's 970.6% raw-engine result."""
    apr = compute_apr_usd_fraction(
        q_me_yu=4.92,
        sigma_yu=75.0,
        side_split=0.760,
        e_liq_per_epoch_pendle=309.96,
        pendle_price_usd=1.35,
        collateral_usd=100.0,
    )
    assert math.isclose(apr, 10.190, rel_tol=2e-3), f"got {apr=}"


def test_share_formula_q_me_4_36_sigma_329_matches_dapp_estimator() -> None:
    """Dapp's While Active/day estimator implicit sigma (~329 YU at t+11.5h) → ~216% APR."""
    apr = compute_apr_usd_fraction(
        q_me_yu=4.36,
        sigma_yu=329.0,
        side_split=0.760,
        e_liq_per_epoch_pendle=309.96,
        pendle_price_usd=1.35,
        collateral_usd=100.0,
    )
    assert math.isclose(apr, 2.163, rel_tol=2e-3), f"got {apr=}"


def test_compute_share_zero_q_me_returns_zero() -> None:
    assert compute_share(0.0, 100.0) == 0.0


def test_compute_share_dominant_q_me_approaches_one() -> None:
    # q_me >> sigma → share → 1.0
    assert compute_share(1_000_000.0, 1.0) > 0.999999


def test_derive_band_pinned_fixture_golden() -> None:
    """Pinned grid sweep against expected (low, mid, high) APR values.

    Inputs match the binding-market replay window for 2026-04-30:
      - sigma anchors: {75, 165, 329}
      - both epochs: prior_split=0.327, current_split=0.760
      - q_me grid: 0.8x, 1.0x, 1.2x of q_max=4.92
    """
    inputs = BandInputs(
        market="BINANCE-ETHUSDT-25SEP2026",
        side="long",
        epoch="both",
        sigma_yu_anchors={"context_md_75": 75.0, "raw_orderbook_in_range": 165.0, "dapp_estimator_implicit": 329.0},
        side_split_prior=0.327,
        side_split_current=0.760,
        q_max_yu=4.92,
        q_me_grid_yu=(4.92 * 0.8, 4.92, 4.92 * 1.2),
        e_liq_per_epoch_pendle=309.96,
        pendle_price_usd=1.35,
        collateral_usd=100.0,
        sigma_source="dapp",
    )
    out = derive_band(inputs, derivation_date_utc="2026-04-30")

    # 3 sigmas × 2 epochs × 3 q_me = 18 cells
    assert len(out.cells) == 18
    # Sanity bounds
    assert out.low_apr > 0.0
    assert out.high_apr > out.mid_apr > out.low_apr
    # Pinned-golden sanity range — band brackets the W5 verdict (970%) and the dapp's
    # estimator implicit (~215%); low is the (sigma=329, prior_split=0.327, q_me=0.8x) cell.
    assert math.isclose(out.low_apr, 0.841, abs_tol=5e-3), f"got low={out.low_apr}"
    assert math.isclose(out.high_apr, 12.068, abs_tol=5e-3), f"got high={out.high_apr}"
    # Mid lies in the empirical "most-realistic" zone (200-500% USD-APR)
    assert 2.0 < out.mid_apr < 5.0


def test_derive_band_deterministic_round_trip() -> None:
    """Same inputs → bit-identical outputs (deterministic; no randomness, no time.time())."""
    inputs = BandInputs(
        market="BINANCE-ETHUSDT-25SEP2026",
        side="long",
        epoch="both",
        sigma_yu_anchors={"a": 100.0, "b": 200.0},
        side_split_prior=0.30,
        side_split_current=0.75,
        q_max_yu=5.0,
        q_me_grid_yu=(4.0, 5.0, 6.0),
        e_liq_per_epoch_pendle=300.0,
        pendle_price_usd=1.35,
        collateral_usd=100.0,
        sigma_source="dapp",
    )
    out1 = derive_band(inputs, derivation_date_utc="2026-04-30")
    out2 = derive_band(inputs, derivation_date_utc="2026-04-30")
    # Identity on numeric fields
    assert out1.low_apr == out2.low_apr
    assert out1.mid_apr == out2.mid_apr
    assert out1.high_apr == out2.high_apr
    assert len(out1.cells) == len(out2.cells)
    for c1, c2 in zip(out1.cells, out2.cells):
        assert c1 == c2


def test_classification_rule_pinned_in_output() -> None:
    """The Phase 05.4-04 T7 classifier reads classification_rule from the band JSON;
    its presence + multipliers must be stable across runs."""
    inputs = BandInputs(
        market="BINANCE-ETHUSDT-25SEP2026",
        side="long",
        epoch="both",
        sigma_yu_anchors={"context_md_75": 75.0, "raw_orderbook_in_range": 165.0, "dapp_estimator_implicit": 329.0},
        side_split_prior=0.327,
        side_split_current=0.760,
        q_max_yu=4.92,
        q_me_grid_yu=(4.92 * 0.8, 4.92, 4.92 * 1.2),
        e_liq_per_epoch_pendle=309.96,
        pendle_price_usd=1.35,
        collateral_usd=100.0,
        sigma_source="dapp",
    )
    out = derive_band(inputs, derivation_date_utc="2026-04-30")

    # Required keys for Phase 05.4-04 T7 consumption
    cr = out.classification_rule
    assert set(cr.keys()) >= {"pass_lo", "pass_hi", "fail_lo", "pass_lo_multiplier", "pass_hi_multiplier", "rationale"}
    # Multiplier values pinned (changing requires updating wiki + this test in same commit)
    assert cr["pass_lo_multiplier"] == 0.5
    assert cr["pass_hi_multiplier"] == 1.5
    assert cr["fail_lo"] == 0.0
    # Derived thresholds match the multipliers
    assert math.isclose(cr["pass_lo"], 0.5 * out.low_apr, rel_tol=1e-9)
    assert math.isclose(cr["pass_hi"], 1.5 * out.high_apr, rel_tol=1e-9)
    # Pinned-fixture absolute values for the binding-market band
    assert math.isclose(cr["pass_lo"], 0.420, abs_tol=5e-3), f"got pass_lo={cr['pass_lo']}"
    assert math.isclose(cr["pass_hi"], 18.10, abs_tol=5e-2), f"got pass_hi={cr['pass_hi']}"
