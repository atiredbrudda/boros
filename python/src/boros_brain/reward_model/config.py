"""RewardShareModelConfig — Pydantic sub-model for REWARD-01/02 knobs.

Re-declares a local StrictBase to avoid circular imports with brain.config.schema
(matches the pattern in brain.fill_model.config + brain.loss_model.config).

Knob inventory (PROTO-04 SSoT):
  - 5 RewardShareModelConfig knobs: competition_poll_interval_s,
    sigma_others_min_pendle, epoch_days, cap_apr_multiple,
    fallback_to_parquet_after_rest_fails_n.

[[reward-cap-geometry-v05]]: cap-budget formula + regime classification.
[[competition-tracker-data-sources-v05]]: Σ_others composition + degraded fallback.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class RewardShareModelConfig(StrictBase):
    """Knobs for the reward-share model + competition tracker (REWARD-01/02).

    All 5 knobs here are the single source of truth (PROTO-04). Adding a knob
    in reward_model code without adding it here is a bug — the manifest
    reflection round-trip catches it.
    """

    competition_poll_interval_s: float = Field(5.0, ge=1.0, le=60.0)
    """How often (seconds) CompetitionTracker.run_one_cycle is invoked."""

    sigma_others_min_pendle: float = Field(1e-6, ge=1e-18, le=1.0)
    """Floor on Σ_others to avoid numerical issues in r_capped denominator."""

    epoch_days: float = Field(7.0, ge=1.0, le=30.0)
    """Reward epoch length (Boros = 7d weekly; Fri 00:00 UTC -> Thu 23:59 UTC)."""

    cap_apr_multiple: float = Field(10.0, ge=1.0, le=100.0)
    """Per-account cap multiple (1000% APR = 10× collateral_usd / year)."""

    fallback_to_parquet_after_rest_fails_n: int = Field(5, ge=1, le=20)
    """After N consecutive REST failures, CompetitionTracker writes
    `data_source='fallback_parquet_only'` and emits `competition_tracker.rest_degraded`."""
