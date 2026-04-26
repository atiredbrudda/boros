"""Pydantic + dataclass shapes for the backtest engine (BACK-01..08).

Single home for all Phase-5 shape declarations so architecture.yml has a single
brain.backtest.schemas node.

[[backtest-output-schema-and-parquet-partitioning]]
[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Local strict base — extra='forbid', frozen=True."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BacktestRunOutput(StrictBase):
    """One row per (run_id, sweep_axis, sweep_value, bootstrap_idx).

    All fields are required except those with defaults. Serialized to Hive-partitioned
    parquet by backtest.report.
    """

    # Provenance
    run_id: str
    parent_run_id: str | None = None
    git_sha: str
    strategy_version: str
    market_id: str
    side: Literal["long", "short"]

    # Sweep coordinates
    sweep_axis: Literal["base", "cancel_latency", "competition", "forfeit_branch", "perturbation"]
    sweep_value: float | str
    bootstrap_idx: int | None = None

    # Core P&L
    raw_pnl_pendle: float
    raw_pnl_usd: float
    annualized_pnl_pct: float
    sharpe_equivalent: float
    max_drawdown_pct: float

    # Activity
    n_decisions: int
    n_fills: int
    n_cancels: int
    n_purges: int
    cumulative_fees_pendle: float
    cumulative_gas_pendle: float

    # Calibration
    predicted_p_fill_mean: float
    realized_fill_rate: float
    calibration_residual: float

    # Lineage flags
    e_liq_data_source: Literal["operator"] = "operator"
    e_liq_calibrated_at: str
    event_index_coverage: Literal["full", "degraded"]
    voluntary_cancel_branch: Literal["benign", "punitive"]

    # Output paths
    parquet_partition: str
    plots_dir: str | None = None


@dataclass(frozen=True)
class ReplayConfig:
    """In-memory configuration for a single ReplayEngine.run() invocation.

    Use this when composing ReplayEngine programmatically. Tests may also construct
    ReplayEngine directly with the flat-keyword constructor.
    """

    config: Any  # BotConfig — use Any to avoid circular import
    market_id: str
    side: Literal["long", "short"]
    parquet_root: Path
    sqlite_path: Path
    cancel_latency_s: float
    voluntary_cancel_branch: Literal["benign", "punitive"] = "benign"
    sigma_others_multiplier: float = 1.0


@dataclass
class ReplayOutput:
    """Output of a single ReplayEngine.run() invocation. Mutable: built up incrementally."""

    rows: list[BacktestRunOutput] = field(default_factory=list)
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    daily_pnl: np.ndarray = field(default_factory=lambda: np.empty(0))
    event_index_coverage: Literal["full", "degraded"] = "full"
    n_amm_violations: int = 0  # MUST stay 0; violations raise AMMConsumptionIdentityError


__all__ = ["StrictBase", "BacktestRunOutput", "ReplayConfig", "ReplayOutput"]
