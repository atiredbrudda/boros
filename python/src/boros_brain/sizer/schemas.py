"""Pydantic shapes for the sizer (REWARD-03/04).

Phase-4 LOCKED contract — DecisionEngine consumes:
    - SizerInput            (sync q_me_target() request shape)
    - SizerOutput           (sync q_me_target() response shape)
    - InsufficientCollateralError (raised when Q_min > Q_max)

Single home for all sizer shape declarations so architecture.yml has a single
`brain.sizer.schemas` node.

[[sizing-optimizer-sub-cap-regime-v05]]
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Local strict base for sizer Pydantic models (avoids circular import
    with config.schema). Matches fill_model/schemas.py + reward_model/schemas.py
    pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SizerInput(StrictBase):
    """Sync q_me_target() request shape — Phase 4 DecisionEngine.

    The reward-side inputs (sigma_others_pendle, e_liq_per_epoch_pendle,
    side_split, t_frac) are supplied by Phase 4 from CompetitionTracker's
    latest state.competition_history row + the MarketRewardCalibration
    operator-supplied calibration in state.market_reward_calibration.
    """

    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    time_to_epoch_end_s: float
    time_to_maturity_s: int
    queue_ahead_wei: int
    current_features: dict[str, float]  # keyed by fill_model covariate_whitelist
    current_chain_ts: int  # caller threads chain_time.now_cached()
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float
    t_frac: float = 1.0


class SizerOutput(StrictBase):
    """Sync q_me_target() response shape — fully-traceable per call.

    `regime` reflects the regime at q_opt (sub_cap / cap_binding /
    market_saturated). All scalar fields below are in PENDLE-units except
    p_fill_at_target (probability) and ev_at_target (PENDLE-units net EV).
    """

    q_me_target_pendle: float
    regime: Literal["sub_cap", "cap_binding", "market_saturated"]
    r_capped_at_target: float
    expected_loss_at_target: float
    p_fill_at_target: float
    ev_at_target: float
    q_min_pendle: float
    q_max_pendle: float
    q_cap_pendle: float


class InsufficientCollateralError(RuntimeError):
    """REWARD-03 — raised by q_me_target() when Q_min > Q_max.

    Collateral can't cover even the minimum order size. Phase 1 economics-gate
    should have caught this earlier; this is a belt-and-braces guard that
    surfaces if an operator attempts a knob combination that produces a
    degenerate sizing interval.
    """

    def __init__(self, q_min: float, q_max: float):
        self.q_min = q_min
        self.q_max = q_max
        super().__init__(
            f"Q_min={q_min} > Q_max={q_max} — collateral too thin for minimum order"
        )
