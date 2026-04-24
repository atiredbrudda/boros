"""Pydantic + Literal shapes for the reward share model (REWARD-01/02/04).

All Pydantic models are local StrictBase (extra='forbid', frozen=True) — same
discipline as fill_model.schemas / loss_model.schemas. Phase-4 LOCKED contracts
the Sizer (Plan 03-03) and DecisionEngine (Phase 4) consume.

[[reward-cap-geometry-v05]] for regime semantics.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


# REWARD-01: regime classifier output
RegimeLabel = Literal["sub_cap", "cap_binding", "market_saturated"]


class RewardCurveInput(StrictBase):
    """Input to r_capped_curve — pure-data shape, no caller-state coupling."""

    market_id: str
    side: Literal["long", "short"]
    q_me_pendle: float
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float  # 0..1
    t_frac: float      # 1.0 for full-epoch posting in v0.5
    collateral_usd: float
    pendle_price_usd: float
    epoch_days: float  # 7.0 locked


class RewardCurveOutput(StrictBase):
    """Output of r_capped_curve. PENDLE-units throughout."""

    r_uncapped_pendle: float
    r_capped_pendle: float
    cap_budget_pendle: float
    regime: RegimeLabel


class CompetitionSnapshot(StrictBase):
    """One row written by CompetitionTracker.run_one_cycle (REWARD-02).

    Mirrors state.competition_history columns. Run-id ties to run_manifests.
    """

    market_id: str
    polled_at_utc: str   # ISO8601
    chain_ts: int
    q_me_pendle: float
    sigma_others_pendle: float
    data_source: Literal["live", "fallback_parquet_only"]
    run_id: str


class MarketRewardCalibrationSplitError(ValueError):
    """P3-4 — raised when long_side_split + short_side_split != 1.0.

    Surfaced by both Pydantic field_validator on MarketRewardCalibration
    (config.schema) and the writer-layer guard in
    state.writers.market_reward_calibration before SQL round-trip.
    """
