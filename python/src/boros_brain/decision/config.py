"""DecisionEngineConfig — Pydantic sub-model for the EV cancel rule + breakers (PROTO-04).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
All ~25 leaf knobs are the single source of truth (PROTO-04). Adding a knob in
decision/ code without adding it here is a bug — test_phase4_manifest_leaves.py
verifies the leaf count.

[[ev-cancel-rule]]: cancel_cost_ewma_alpha, p_purge_default used in engine.evaluate
[[circuit-breakers-v05]]: 10 per-breaker sub-models in BreakerConfig
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    """Strict frozen base — mirrors fill_model/config.py pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ── Per-breaker config classes (10) ─────────────────────────────────────────


class MarginBreakerConfig(StrictBase):
    """SAFE-01: Margin trajectory breaker config knobs."""

    window_s: float = Field(30.0, ge=5.0, le=600.0)
    """Sliding window for linear regression on net_margin_usd samples (seconds)."""

    min_samples: int = Field(10, ge=2, le=200)
    """Minimum number of margin_history rows required before the breaker can fire."""

    time_to_mm_threshold_s: float = Field(300.0, ge=5.0, le=3600.0)
    """Trip if extrapolated time to maintenance margin < this value (seconds).

    Default 300s (5 minutes): provides early-warning headroom on the 1 Hz
    decision loop — at $100 collateral a -1 USD/s slope gives ~70-90s to
    maintenance margin which should fire the breaker predictively rather than
    reactively.  Raised upper bound to 3600s (1h) from 600s to allow operators
    on slow-decaying markets to configure wider prediction horizons.
    """

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class OracleStaleBreakerConfig(StrictBase):
    """SAFE-02: Oracle staleness breaker config knobs."""

    fraction_of_max: float = Field(0.7, ge=0.1, le=1.0)
    """Trip when (now - fTime) > fraction_of_max * maxUpdateDelay."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class CloRemovalBreakerConfig(StrictBase):
    """SAFE-03: CLO removal breaker config knobs."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class CloShiftBreakerConfig(StrictBase):
    """SAFE-04: CLO shift breaker config knobs."""

    n_ticks: int = Field(5, ge=1, le=100)
    """Trip if |new_clo - old_clo| > n_ticks (in tick units)."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class FillRateBreakerConfig(StrictBase):
    """SAFE-05: Fill-rate runaway breaker config knobs."""

    k_fills_per_hour: int = Field(3, ge=1, le=100)
    """Trip if confirmed fills in the last 60 minutes exceeds this count."""

    min_re_arm_s: float = Field(600.0, ge=0.0, le=3600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class CompetitionBreakerConfig(StrictBase):
    """SAFE-06: Competition collapse breaker config knobs."""

    drop_threshold: float = Field(0.5, ge=0.01, le=1.0)
    """Trip if Q_total_in_range dropped by more than this fraction in 1 epoch."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class MaturityBreakerConfig(StrictBase):
    """SAFE-07: Maturity migration breaker config knobs."""

    migration_cost_buffer_pct: float = Field(1.0, ge=0.0, le=100.0)
    """Buffer as a percentage of estimated migration cost — ensures a safety margin."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class SideBudgetBreakerConfig(StrictBase):
    """SAFE-08: Per-side budget rebalance breaker config knobs."""

    drift_threshold: float = Field(0.30, ge=0.01, le=1.0)
    """Trip if long_side_split or short_side_split shifted by >= this fraction."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class UnderlyingStaleBreakerConfig(StrictBase):
    """SAFE-09: Underlying feed staleness breaker config knobs."""

    expected_cadence_s_per_exchange: dict[str, float] = Field(
        default_factory=lambda: dict(binance=28800.0, okx=3600.0, hyperliquid=60.0)
    )
    """Expected update cadence in seconds per exchange. Trip if last_updated_ts
    is older than 2× the expected cadence for the underlying_exchange."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


class LossFitDegradedBreakerConfig(StrictBase):
    """B5 absorbed — OU-fit-degraded breaker config knobs."""

    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)
    """Minimum seconds after first trip before the breaker can fire again."""


# ── BreakerConfig — top-level container for all 10 per-breaker sub-models ──


class BreakerConfig(StrictBase):
    """Container for the 10 per-breaker config sub-models."""

    margin: MarginBreakerConfig = Field(default_factory=MarginBreakerConfig)  # type: ignore
    oracle_stale: OracleStaleBreakerConfig = Field(default_factory=OracleStaleBreakerConfig)  # type: ignore
    clo_removal: CloRemovalBreakerConfig = Field(default_factory=CloRemovalBreakerConfig)  # type: ignore
    clo_shift: CloShiftBreakerConfig = Field(default_factory=CloShiftBreakerConfig)  # type: ignore
    fill_rate: FillRateBreakerConfig = Field(default_factory=FillRateBreakerConfig)  # type: ignore
    competition: CompetitionBreakerConfig = Field(default_factory=CompetitionBreakerConfig)  # type: ignore
    maturity: MaturityBreakerConfig = Field(default_factory=MaturityBreakerConfig)  # type: ignore
    side_budget: SideBudgetBreakerConfig = Field(default_factory=SideBudgetBreakerConfig)  # type: ignore
    underlying_stale: UnderlyingStaleBreakerConfig = Field(default_factory=UnderlyingStaleBreakerConfig)  # type: ignore
    loss_fit_degraded: LossFitDegradedBreakerConfig = Field(default_factory=LossFitDegradedBreakerConfig)  # type: ignore


# ── DecisionEngineConfig — top-level ────────────────────────────────────────


class DecisionEngineConfig(StrictBase):
    """Top-level config for the decision engine + all breakers (PROTO-04 SSoT).

    The ~25 leaf knobs below are reflection-surfaced in RUN_MANIFEST via
    BotConfig.model_dump(). Adding a knob in decision/ code without adding it
    here is mechanically caught by test_phase4_manifest_leaves.py.
    """

    cancel_cost_ewma_alpha: float = Field(0.1, ge=0.0, le=1.0)
    """EWMA alpha for gas fee history (DECIDE-03). Half-life ≈ 7 blocks at α=0.1."""

    cancel_cost_ttl_s: float = Field(60.0, ge=1.0, le=600.0)
    """TTL in seconds for the cancel_cost cache. One RPC call per minute."""

    cancel_cost_block_window: int = Field(100, ge=10, le=1000)
    """Number of recent blocks to fetch for the gas EWMA. 100 ≈ 25s on Arbitrum."""

    p_purge_default: float = Field(0.0, ge=0.0, le=1.0)
    """Default P(purge) used if purge probability is not otherwise supplied."""

    decision_loop_interval_s: float = Field(1.0, ge=0.1, le=10.0)
    """Interval in seconds for the 1 Hz decision loop."""

    breakers: BreakerConfig = Field(default_factory=BreakerConfig)  # type: ignore
    """Container for all 10 per-breaker config sub-models."""


__all__ = [
    "DecisionEngineConfig",
    "BreakerConfig",
    "MarginBreakerConfig",
    "OracleStaleBreakerConfig",
    "CloRemovalBreakerConfig",
    "CloShiftBreakerConfig",
    "FillRateBreakerConfig",
    "CompetitionBreakerConfig",
    "MaturityBreakerConfig",
    "SideBudgetBreakerConfig",
    "UnderlyingStaleBreakerConfig",
    "LossFitDegradedBreakerConfig",
]
