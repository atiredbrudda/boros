"""REWARD-04 closed-form Q_cap algebra.

Boundary where R_uncapped(Q_me) first hits cap_budget. From the consolidated
plan §4 step 4:

    Q_cap = Σ_others × cap_budget / (E_liq × side_split × t_frac - cap_budget × t_frac)

Returns math.inf when cap is algebraically unreachable at any finite Q_me
(denominator <= 0).

At $100 collateral on the ETHUSDT-29MAY2026 anchor (cap_budget ≈ 0.274 PENDLE,
E_liq × side_split ≈ 234 PENDLE), Q_cap is finite but LARGER than the
collateral-constrained Q_max at $100 — so it never practically binds. At $5000
collateral (cap_budget ≈ 13.7 PENDLE), Q_cap is smaller AND smaller than Q_max
— cap binds.

[[reward-cap-geometry-v05]]
"""
from __future__ import annotations

import math

__all__ = ["compute_q_cap"]


def compute_q_cap(
    *,
    sigma_others_pendle: float,
    e_liq_per_epoch_pendle: float,
    side_split: float,
    t_frac: float,
    collateral_usd: float,
    pendle_price_usd: float,
    epoch_days: float,
) -> float:
    """Return the Q_me at which R_uncapped first equals cap_budget.

    Returns math.inf when the cap is algebraically unreachable at any finite
    Q_me (denominator <= 0 — cap_budget >= E_liq × side_split × t_frac).
    """
    if pendle_price_usd <= 0.0:
        raise ValueError(
            f"pendle_price_usd must be > 0, got {pendle_price_usd}"
        )
    if epoch_days <= 0.0:
        raise ValueError(f"epoch_days must be > 0, got {epoch_days}")

    cap_budget = (
        10.0
        * collateral_usd
        * (epoch_days / 365.0)
        / pendle_price_usd
    )

    numerator = sigma_others_pendle * cap_budget
    denominator = (
        e_liq_per_epoch_pendle * side_split * t_frac - cap_budget * t_frac
    )

    if denominator <= 0.0:
        # Cap is at or above E_liq × side_split × t_frac — unreachable at any finite Q_me.
        return math.inf

    return numerator / denominator
