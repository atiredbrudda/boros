"""REWARD-01 closed-form capped pro-rata reward-share formula.

Verbatim from boros_consolidated_plan.md §4 step 4. PENDLE-unit discipline.
Fees are NOT subtracted here — they're absorbed inside LossModel.expected_loss
(see [[fee-cost-term-in-expected-loss]]). This matches the EV-rule derivation
where R_capped is the revenue side and E[loss|fill] × P(fill) is the cost side.

PITFALLS §A4 absorption: returns three-way `regime` classification ('sub_cap',
'cap_binding', 'market_saturated') alongside the capped share. Kinked-curve
geometry is thus observable to Phase 4 DecisionEngine.

[[reward-cap-geometry-v05]]
"""

from __future__ import annotations

from typing import Literal

import structlog

# noqa: F401 — reused pattern (may inform docs); our formula uses epoch_days directly.
from ..screener.economics_gate import EPOCHS_PER_YEAR  # noqa: F401
from .schemas import RewardCurveInput, RewardCurveOutput

log = structlog.get_logger(__name__)

__all__ = ["r_capped_curve"]


def r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput:
    """Compute R_uncapped, R_capped, cap_budget, and regime label.

    Formula:
        R_uncapped = E_liq × side_split × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)
        cap_budget = 10 × collateral_usd × (epoch_days / 365) / pendle_price_usd
        R_capped   = min(R_uncapped, cap_budget)

    Regimes:
        - market_saturated: Σ_others == 0 AND Q_me > 0 (we have the market to ourselves)
        - cap_binding:      R_uncapped >= cap_budget (the cap clips the curve)
        - sub_cap:          otherwise (the healthy regime at $100 collateral)

    Units: all outputs in PENDLE.

    T-03-03 mitigation: explicit `denom == 0.0 or q_me == 0.0` guard at formula
    entry. Mirrors screener/economics_gate.py divide-by-zero pattern.
    """
    # Input validation (fail closed on operator / caller errors).
    if req.pendle_price_usd <= 0.0:
        raise ValueError(f"pendle_price_usd must be > 0, got {req.pendle_price_usd}")
    if req.e_liq_per_epoch_pendle < 0.0:
        raise ValueError(f"e_liq_per_epoch_pendle must be >= 0.0, got {req.e_liq_per_epoch_pendle}")
    if req.epoch_days <= 0.0:
        raise ValueError(f"epoch_days must be > 0, got {req.epoch_days}")

    # r_uncapped with div-by-zero guard (T-03-03 mitigation).
    denom = req.sigma_others_pendle + req.q_me_pendle * req.t_frac
    if denom == 0.0 or req.q_me_pendle == 0.0:
        r_uncapped = 0.0
    else:
        r_uncapped = req.e_liq_per_epoch_pendle * req.side_split * (req.q_me_pendle * req.t_frac) / denom

    # cap_budget_per_epoch in PENDLE-units (A4 kink point).
    cap_budget = 10.0 * req.collateral_usd * (req.epoch_days / 365.0) / req.pendle_price_usd

    # Regime classification — order matters: market_saturated takes priority over
    # cap_binding when Σ=0 and Q_me>0 (the formula returns full E_liq×side_split,
    # which CAN exceed cap_budget at scaled-up collateral but the geometric
    # interpretation is "we own the market" rather than "cap clipped a busy market").
    regime: Literal["sub_cap", "cap_binding", "market_saturated"]
    if req.sigma_others_pendle == 0.0 and req.q_me_pendle > 0.0:
        regime = "market_saturated"
    elif r_uncapped >= cap_budget:
        regime = "cap_binding"
    else:
        regime = "sub_cap"

    r_capped = min(r_uncapped, cap_budget)

    return RewardCurveOutput(
        r_uncapped_pendle=r_uncapped,
        r_capped_pendle=r_capped,
        cap_budget_pendle=cap_budget,
        regime=regime,
    )
