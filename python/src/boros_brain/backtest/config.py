"""BacktestConfig — Pydantic sub-model for Phase 5 knobs (PROTO-04).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
All ~10 leaf knobs are the single source of truth (PROTO-04). Adding a knob in
backtest/ code without adding it here is a bug — test_phase5_manifest_leaves.py
verifies every knob round-trips through manifest reflection.

[[backtest-bootstrap-methodology-v05]]
[[backtest-ship-gate-threshold-assembly]]
[[backtest-perturbation-grid-pydantic-reflection]]
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BacktestConfig(StrictBase):
    """Top-level config for the Phase-5 backtest harness (PROTO-04 SSoT)."""

    bootstrap_n_resamples: int = Field(2000, ge=100, le=100_000)
    bootstrap_block_seconds: int = Field(86400, ge=3600, le=604800)
    cancel_latency_grid: list[float] = Field(default_factory=lambda: [0.5, 1.0, 2.0, 3.0, 5.0, 10.0])

    @field_validator("cancel_latency_grid")
    @classmethod
    def _validate_latency_grid(cls, v: list[float]) -> list[float]:
        if not (1 <= len(v) <= 20):
            raise ValueError("cancel_latency_grid must have 1..20 elements")
        if any(x < 0.001 or x > 60.0 for x in v):
            raise ValueError("cancel_latency_grid elements must be in [0.001, 60.0]")
        return v

    competition_multipliers: list[float] = Field(default_factory=lambda: [0.5, 0.75, 1.0, 1.5, 2.0, 3.0])
    all_fees_threshold: float = Field(0.01, ge=0.0, le=1.0)
    budget_haircut_pessimistic: float = Field(0.5, ge=0.0, le=1.0)
    perturbation_pct: float = Field(0.20, ge=0.01, le=1.0)
    contour_2d_knobs: list[str] = Field(
        default_factory=lambda: [
            "execution.cancel_latency_budget_s",
            "screener.alt_yield",
        ],
        min_length=2,
        max_length=2,
    )
    output_parquet_root: str = "data/parquet/backtest_results"
    voluntary_cancel_divergence_warn_pct: float = Field(0.10, ge=0.0, le=1.0)


__all__ = ["BacktestConfig"]
