"""Pydantic shapes for the decision engine (DECIDE-01/02/03/04).

Single home for all decision shape declarations so architecture.yml has a single
`brain.decision.schemas` node.

[[ev-cancel-rule]]: EV = R_share * P(no_fill) - E[loss|fill] * P(fill) - cancel_cost * P(purge)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Local strict base — extra='forbid', frozen=True.

    Mirrors loss_model/schemas.py pattern (avoids circular import with config.schema).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluateInput(StrictBase):
    """Inputs to a single decision engine evaluation (DECIDE-01).

    One instance per (order_id, side) per 1 Hz cycle. All 16 fields are required.
    """

    market_id: str
    side: Literal["long", "short"]
    order_id: str
    depth_from_mark_ticks: int
    queue_ahead_wei: int
    current_features: dict[str, float]
    time_to_epoch_end_s: float
    time_to_maturity_s: int
    q_me_pendle: float
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float
    t_frac: float
    p_purge: float
    r_me_per_epoch_pendle_accumulated_so_far: float
    current_chain_ts: int


class EvaluateOutput(StrictBase):
    """Outputs of a single decision engine evaluation (DECIDE-01/02).

    Contains the full audit trail for the decision log.
    """

    decision_kind: Literal["CANCEL", "HOLD", "PLACE"]
    ev_hold_pendle: float
    r_share_per_epoch_pendle: float
    p_no_fill_and_unpurged: float
    e_loss_pendle: float
    p_fill: float
    cancel_cost_pendle: float
    p_purge: float
    fit_status_fill: Literal["ok", "degraded", "stale"]
    fit_status_loss: Literal["ok", "degraded", "stale"]
    voluntary_cancel_branch: Literal["benign", "punitive"]
    reasoning: dict[str, Any]


__all__ = ["StrictBase", "EvaluateInput", "EvaluateOutput"]
