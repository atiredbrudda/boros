"""LossModelConfig + FeesConfig — Pydantic sub-models for the loss model (LOSS-01/02/03).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
This mirrors the pattern in brain.fill_model.config.

Knob inventory (PROTO-04 SSoT):
  - 12 LossModelConfig knobs: depth_bucket_edges, tau_bucket_edges_days, min_samples_per_cell,
    knn_k, knn_max_distance, aggregation_metric, window_days, refit_cadence_s,
    fit_warn_staleness_s, fit_max_staleness_s, close_latency_budget_s, fees.
  - 8 FeesConfig knobs: taker_fee_rate, settlement_fee_rate, settlement_period_s,
    market_entrance_fee_usd, gas_place_gwei, gas_cancel_gwei, gas_close_gwei, gas_price_gwei.

[[empirical-loss-grid-v05]]: bucket-edge convention + sparse-cell fallback policy.
[[fee-cost-term-in-expected-loss]]: A6 absorption — fees enter the per-fill P&L integrand.

Bucket-edge sentinel: 10000.0 instead of an infinity literal. Pydantic JSON dump
emits 'Infinity' which YAML cannot re-parse (PATTERNS §config.py gotcha).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class FeesConfig(StrictBase):
    """A6 absorption — fees that enter the E[loss|fill] integrand.

    Default values from [[fee-schedule]] (resolved 2026-04-23 from Pendle docs).
    """

    taker_fee_rate: float = Field(5e-4, ge=0.0, le=0.01)
    """Per-fill taker fee rate (0.05% Boros default; maker is 0)."""

    settlement_fee_rate: float = Field(1e-3, ge=0.0, le=0.01)
    """Per-settlement-window fee rate (0.1% non-discountable)."""

    settlement_period_s: int = Field(28800, ge=3600, le=86400)
    """Settlement-period length in seconds (8h typical)."""

    market_entrance_fee_usd: float = Field(1.0, ge=0.0, le=10.0)
    """One-time per-market entrance fee in USD (~$1 typical, amortized over fills)."""

    gas_place_gwei: int = Field(200000, ge=50000, le=2000000)
    """Gas units consumed by an order-placement tx (Arbitrum)."""

    gas_cancel_gwei: int = Field(100000, ge=20000, le=1000000)
    """Gas units consumed by an order-cancel tx (Arbitrum)."""

    gas_close_gwei: int = Field(300000, ge=100000, le=3000000)
    """Gas units consumed by an immediate-close-at-market tx (Arbitrum)."""

    gas_price_gwei: float = Field(0.1, ge=0.01, le=10.0)
    """Effective gas price in gwei (Arbitrum 0.1 typical)."""


class LossModelConfig(StrictBase):
    """Knobs for the empirical loss-grid model + OU scaffold (LOSS-01/02/03).

    All 12 knobs here are the single source of truth (PROTO-04). Adding a knob in
    loss_model code without adding it here is a bug — manifest reflection round-trip
    catches it.

    NOTE: an infinity literal in Pydantic JSON-dump emits "Infinity" which YAML
    cannot re-parse. Using finite sentinel 10000.0 (10000 ticks / 10000 days) per
    PATTERNS §config.py gotcha.
    """

    depth_bucket_edges: list[float] = Field(default_factory=lambda: [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0])
    """Bin edges for depth_from_mark_ticks. Terminal sentinel 10000.0 (not inf)."""

    tau_bucket_edges_days: list[float] = Field(
        default_factory=lambda: [0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0]
    )
    """Bin edges for tau_days (time-to-maturity). Terminal sentinel 10000.0 (not inf)."""

    min_samples_per_cell: int = Field(5, ge=1, le=100)
    """Below this n_samples threshold a cell falls back to k-NN or coarse_bound."""

    knn_k: int = Field(3, ge=1, le=10)
    """Number of nearest-neighbor cells to aggregate when target cell is sparse."""

    knn_max_distance: float = Field(4.0, ge=1.0, le=16.0)
    """Maximum Euclidean bucket-index distance for k-NN inclusion."""

    aggregation_metric: Literal["mean", "p50", "p95"] = "mean"
    """Per-cell aggregation surfaced by expected_loss(). p95 = pessimistic."""

    window_days: int = Field(90, ge=14, le=365)
    """Rolling history window for loss-grid refit (longer than fill_model — fills are rarer)."""

    refit_cadence_s: float = Field(900.0, ge=60.0, le=86400.0)
    """How often (seconds) refit_loop reruns fit_loss_grid."""

    fit_warn_staleness_s: float = Field(1800.0, ge=600.0, le=14400.0)
    """Emit loss_model.expected_loss_stale_grid warning above this fit age."""

    fit_max_staleness_s: float = Field(86400.0, ge=3600.0, le=604800.0)
    """Raise LossModelNoFreshGridError above this fit age."""

    close_latency_budget_s: float = Field(60.0, ge=5.0, le=600.0)
    """Maximum wall-clock window over which an opposite-side close trade may be matched
    in replay. Fills with no close inside this window are skipped (no look-ahead, no
    silent close-rate fabrication)."""

    fees: FeesConfig = Field(default_factory=FeesConfig)  # type: ignore
    """Nested fee knobs — PROTO-04 SSoT for fee absorption in E[loss|fill]."""
