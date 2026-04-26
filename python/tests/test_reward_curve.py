"""REWARD-01 + REWARD-04 closed-form tests.

ETHUSDT-29MAY2026 anchor (from boros_consolidated_plan.md §4):
    E_liq_per_epoch_pendle = 273.0 (short-side budget)
    Σ_others_pendle         = 60.0
    side_split              = 0.86 (short side)
    pendle_price_usd        = 7.0
    epoch_days              = 7.0

Phase 3 Success Criterion #2 from the ROADMAP — RewardShareModel.R_capped(Q_me)
at $100 collateral produces sub_cap-labeled curve, and the cap-binding branch
unit test passes at scaled-up collateral inputs.
"""

from __future__ import annotations

import math

import pytest

from boros_brain.reward_model.q_cap import compute_q_cap
from boros_brain.reward_model.r_capped import r_capped_curve
from boros_brain.reward_model.schemas import RewardCurveInput

# Anchor params
MKT = "BINANCE-ETHUSDT-29MAY2026"
E_LIQ = 273.0
SIGMA = 60.0
SIDE_SPLIT = 0.86
T_FRAC = 1.0
PENDLE_USD = 7.0
EPOCH_DAYS = 7.0


def _build_req(**overrides) -> RewardCurveInput:
    params = dict(
        market_id=MKT,
        side="short",
        q_me_pendle=0.001,
        sigma_others_pendle=SIGMA,
        e_liq_per_epoch_pendle=E_LIQ,
        side_split=SIDE_SPLIT,
        t_frac=T_FRAC,
        collateral_usd=100.0,
        pendle_price_usd=PENDLE_USD,
        epoch_days=EPOCH_DAYS,
    )
    params.update(overrides)
    return RewardCurveInput(**params)


def test_sub_cap_regime() -> None:
    """REWARD-01: at $100, Q_me=Q_min, regime=sub_cap and r_capped < cap_budget."""
    req = _build_req(collateral_usd=100.0, q_me_pendle=0.001)
    out = r_capped_curve(req)
    assert out.regime == "sub_cap"
    # r_uncapped = 273 × 0.86 × 0.001 / (60 + 0.001) ≈ 0.00391
    expected_r_uncapped = 273.0 * 0.86 * 0.001 / (60.0 + 0.001)
    assert out.r_uncapped_pendle == pytest.approx(expected_r_uncapped, rel=1e-6)
    # cap_budget = 10 × 100 × 7/365 / 7 ≈ 0.2740
    expected_cap = 10.0 * 100.0 * 7.0 / 365.0 / 7.0
    assert out.cap_budget_pendle == pytest.approx(expected_cap, rel=1e-6)
    assert out.r_capped_pendle == out.r_uncapped_pendle
    assert out.r_uncapped_pendle < out.cap_budget_pendle


def test_cap_binding_regime() -> None:
    """REWARD-01: at $5000, push Q_me=100 PENDLE; r_uncapped ≫ cap, regime=cap_binding."""
    req = _build_req(collateral_usd=5000.0, q_me_pendle=100.0)
    out = r_capped_curve(req)
    # r_uncapped = 273 × 0.86 × 100 / (60 + 100) = 146.74
    expected_r_uncapped = 273.0 * 0.86 * 100.0 / (60.0 + 100.0)
    assert out.r_uncapped_pendle == pytest.approx(expected_r_uncapped, rel=1e-6)
    # cap_budget = 10 × 5000 × 7/365 / 7 ≈ 13.70
    expected_cap = 10.0 * 5000.0 * 7.0 / 365.0 / 7.0
    assert out.cap_budget_pendle == pytest.approx(expected_cap, rel=1e-6)
    assert out.regime == "cap_binding"
    assert out.r_capped_pendle == pytest.approx(expected_cap, rel=1e-6)


def test_market_saturated_regime() -> None:
    """REWARD-01: Σ_others=0, Q_me>0 → market_saturated, r_uncapped = E_liq × side_split."""
    req = _build_req(sigma_others_pendle=0.0, q_me_pendle=1.0)
    out = r_capped_curve(req)
    assert out.regime == "market_saturated"
    # r_uncapped = 273 × 0.86 × 1 / (0 + 1) = 234.78
    assert out.r_uncapped_pendle == pytest.approx(273.0 * 0.86, rel=1e-6)


def test_q_me_zero() -> None:
    """Guard: Q_me=0 → r_uncapped=0, regime=sub_cap."""
    req = _build_req(q_me_pendle=0.0)
    out = r_capped_curve(req)
    assert out.r_uncapped_pendle == 0.0
    assert out.regime == "sub_cap"


def test_r_capped_no_div_by_zero() -> None:
    """T-03-03 mitigation: Σ_others=0 AND Q_me=0 → no crash."""
    req = _build_req(sigma_others_pendle=0.0, q_me_pendle=0.0)
    out = r_capped_curve(req)
    # Both guards trigger; r_uncapped=0, regime=sub_cap (Q_me=0 path wins).
    assert out.r_uncapped_pendle == 0.0
    assert out.regime == "sub_cap"


def test_pendle_price_zero_raises() -> None:
    with pytest.raises(ValueError, match="pendle_price_usd must be > 0"):
        r_capped_curve(_build_req(pendle_price_usd=0.0))


def test_negative_e_liq_raises() -> None:
    with pytest.raises(ValueError, match="e_liq_per_epoch_pendle must be >= 0.0"):
        r_capped_curve(_build_req(e_liq_per_epoch_pendle=-1.0))


def test_q_cap_inf_when_cap_unreachable() -> None:
    """REWARD-04 degenerate path: when cap_budget >= E_liq × side_split, Q_cap = inf."""
    # E_liq tiny → cap always unreachable at any finite Q_me.
    q_cap = compute_q_cap(
        sigma_others_pendle=60.0,
        e_liq_per_epoch_pendle=0.001,  # very small
        side_split=0.86,
        t_frac=1.0,
        collateral_usd=100.0,
        pendle_price_usd=7.0,
        epoch_days=7.0,
    )
    assert math.isinf(q_cap)


def test_q_cap_finite_at_100_collateral_ethusdt() -> None:
    """REWARD-04: at $100 ETHUSDT anchor, Q_cap is FINITE but > Q_min.

    cap_budget = 10 × 100 × 7/365 / 7 = 100/365 ≈ 0.274 ... wait that's
    actually `10 * 100 * (7/365) / 7 = 1000/365 ≈ 2.74` PENDLE per epoch
    (left-to-right evaluation: 10*100=1000, *7/365=19.18, /7=2.74).

    Q_cap = Σ × cap_budget / (E_liq × side_split × t_frac - cap_budget × t_frac)
          = 60 × 2.74 / (234.78 - 2.74)
          = 164.4 / 232.04 ≈ 0.708 PENDLE.

    Q_min at $100 is ≈ 1e-3 PENDLE (collateral-constrained), so Q_cap ≫ Q_min →
    cap never practically binds.
    """
    q_cap = compute_q_cap(
        sigma_others_pendle=60.0,
        e_liq_per_epoch_pendle=273.0,
        side_split=0.86,
        t_frac=1.0,
        collateral_usd=100.0,
        pendle_price_usd=7.0,
        epoch_days=7.0,
    )
    # Range chosen empirically — bracket value ≈ 0.71 PENDLE.
    assert 0.1 < q_cap < 5.0, f"expected Q_cap in (0.1, 5.0) PENDLE, got {q_cap}"
    # Q_cap >> typical Q_min=1e-3 at $100 → cap doesn't practically bind.
    assert q_cap > 0.001


def test_q_cap_at_5k_collateral() -> None:
    """REWARD-04: at $5000 ETHUSDT, cap_budget = 137 PENDLE.

    Q_cap = 60 × 137 / (234.78 - 137) = 8220 / 97.78 ≈ 84 PENDLE.

    (Note: this is much larger than at $100 because cap_budget scales
    linearly with collateral while E_liq × side_split is held fixed —
    pushes the algebraic Q_cap higher. The cap STILL practically binds
    at $5000 because Q_max is also large enough to reach it.)
    """
    q_cap = compute_q_cap(
        sigma_others_pendle=60.0,
        e_liq_per_epoch_pendle=273.0,
        side_split=0.86,
        t_frac=1.0,
        collateral_usd=5000.0,
        pendle_price_usd=7.0,
        epoch_days=7.0,
    )
    # Bracket value ≈ 84 PENDLE.
    assert 50.0 < q_cap < 200.0, f"expected Q_cap in (50, 200) PENDLE at $5k, got {q_cap}"


def test_q_cap_pendle_price_zero_raises() -> None:
    with pytest.raises(ValueError):
        compute_q_cap(
            sigma_others_pendle=60.0,
            e_liq_per_epoch_pendle=273.0,
            side_split=0.86,
            t_frac=1.0,
            collateral_usd=100.0,
            pendle_price_usd=0.0,
            epoch_days=7.0,
        )


def test_monotone_non_decreasing_in_q_me() -> None:
    """Property: r_capped(Q_me) is monotone non-decreasing in Q_me in sub_cap regime.

    Sub_cap: r_capped = r_uncapped. r_uncapped(Q) = E_liq × ss × (Q × t) / (Σ + Q × t).
    First derivative wrt Q: positive (Σ > 0). Sanity-check at 3 points.
    """
    out_low = r_capped_curve(_build_req(q_me_pendle=0.001))
    out_mid = r_capped_curve(_build_req(q_me_pendle=0.01))
    out_high = r_capped_curve(_build_req(q_me_pendle=0.05))
    assert out_low.r_capped_pendle <= out_mid.r_capped_pendle <= out_high.r_capped_pendle
