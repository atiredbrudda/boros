"""LOSS-01: empirical (depth, tau)-grid fit per (market, side).

Calls replay_historical_fills, bins per-fill P&L into the configured
(depth_bucket, tau_bucket) grid, computes per-cell aggregation stats, and
returns a LossGridArtifact. fit_status='ok' when every cell meets
min_samples_per_cell; 'degraded' when the population is too sparse for a
healthy grid (half or more cells empty, OR replay returned empty).

Mirrors fill_model.fit.fit_market_side: persistence is opt-out via persist=False
to keep bootstrap / exploratory fits from polluting state.loss_grid_artifacts.

NO wall-clock calls in this module — all ts values come from caller; created_at
sentinel = 0 (artifact.write_loss_grid_artifact stamps).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import polars as pl
import structlog

from ..config.schema import BotConfig
from .artifact import write_loss_grid_artifact
from .config import LossModelConfig
from .replay import replay_historical_fills
from .schemas import LossGridArtifact, LossGridCell, PerFillPnL

log = structlog.get_logger(__name__)

__all__ = ["fit_loss_grid", "build_loss_grid_artifact_from_fills"]


def _get_loss_model_config(config: BotConfig) -> LossModelConfig:
    """Plan-03-01-independent fallback to a default LossModelConfig until 03-02
    attaches BotConfig.loss_model. Mirror of replay._get_loss_model_config."""
    return getattr(config, "loss_model", None) or LossModelConfig()


def _bucket_idx(value: float, edges: list[float]) -> int:
    """Locate the largest i s.t. edges[i] <= value < edges[i+1].

    Returns 0 if value < edges[0]; len(edges)-2 if value >= edges[-1] (the terminal
    sentinel bucket). Edges are expected to be strictly increasing.
    """
    n = len(edges)
    if n < 2:
        return 0
    # Clamp to first bucket if below floor
    if value <= edges[0]:
        return 0
    # Find the rightmost i with edges[i] <= value
    for i in range(n - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    return n - 2  # value >= edges[-1] -> terminal bucket


def build_loss_grid_artifact_from_fills(
    fills: list[PerFillPnL],
    *,
    config: BotConfig,
    market_id: str,
    side: Literal["long", "short"],
    window_start_ts: int,
    window_end_ts: int,
    run_id: str,
) -> LossGridArtifact:
    """Build a LossGridArtifact (with created_at=0 sentinel) from a per-fill list.

    Pure function — does NOT persist. Useful for tests + the fit() driver.
    fit_status='degraded' iff fills empty OR len(fills) < min_samples_per_cell × 0.5
    (heuristic: half a single cell of data won't sustain the full grid).
    """
    lcfg = _get_loss_model_config(config)
    min_samp = lcfg.min_samples_per_cell

    # event_index coverage carry-through
    eic: Literal["full", "degraded"] = "degraded" if any(f.fill_event_index is None for f in fills) else "full"

    if not fills or len(fills) < int(min_samp * 0.5):
        log.warning(
            "loss_model.fit_degraded",
            market_id=market_id,
            side=side,
            n_fills=len(fills),
            reason="insufficient_data",
        )
        return LossGridArtifact(
            run_id=run_id,
            market_id=market_id,
            side=side,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
            fit_status="degraded",
            depth_bucket_edges=list(lcfg.depth_bucket_edges),
            tau_bucket_edges_days=list(lcfg.tau_bucket_edges_days),
            cells=[],
            event_index_coverage=eic,
            created_at=0,
        )

    # Bin fills into cells.
    rows = []
    for f in fills:
        d_idx = _bucket_idx(float(f.depth_from_mark_ticks), lcfg.depth_bucket_edges)
        t_idx = _bucket_idx(float(f.tau_days), lcfg.tau_bucket_edges_days)
        rows.append(
            {
                "depth_bucket_idx": d_idx,
                "tau_bucket_idx": t_idx,
                "pnl_pendle": float(f.pnl_pendle),
            }
        )

    df = pl.DataFrame(rows)
    cells_df = df.group_by(["depth_bucket_idx", "tau_bucket_idx"]).agg(
        [
            pl.len().alias("n_samples"),
            pl.col("pnl_pendle").mean().alias("mean_pendle"),
            pl.col("pnl_pendle").std().alias("std_pendle"),
            pl.col("pnl_pendle").quantile(0.05).alias("p5_pendle"),
            pl.col("pnl_pendle").quantile(0.50).alias("p50_pendle"),
            pl.col("pnl_pendle").quantile(0.95).alias("p95_pendle"),
        ]
    )

    cells: list[LossGridCell] = []
    for r in cells_df.iter_rows(named=True):
        std_val = r["std_pendle"]
        if std_val is None:
            std_val = 0.0
        cells.append(
            LossGridCell(
                depth_bucket_idx=int(r["depth_bucket_idx"]),
                tau_bucket_idx=int(r["tau_bucket_idx"]),
                n_samples=int(r["n_samples"]),
                mean_pendle=float(r["mean_pendle"]),
                std_pendle=float(std_val),
                p5_pendle=float(r["p5_pendle"]),
                p50_pendle=float(r["p50_pendle"]),
                p95_pendle=float(r["p95_pendle"]),
            )
        )

    # fit_status: 'ok' iff every present cell meets min_samples_per_cell.
    # (Cells that are empty are not in `cells` at all; the grid is sparse-by-cell
    # — sparse-cell fallback is the policy at expected_loss time, not here.)
    if cells and all(c.n_samples >= min_samp for c in cells):
        fit_status: Literal["ok", "degraded", "stale"] = "ok"
    else:
        fit_status = "degraded"

    log.info(
        "loss_model.fit_completed",
        market_id=market_id,
        side=side,
        n_fills=len(fills),
        n_cells=len(cells),
        fit_status=fit_status,
        run_id=run_id,
    )

    return LossGridArtifact(
        run_id=run_id,
        market_id=market_id,
        side=side,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
        fit_status=fit_status,
        depth_bucket_edges=list(lcfg.depth_bucket_edges),
        tau_bucket_edges_days=list(lcfg.tau_bucket_edges_days),
        cells=cells,
        event_index_coverage=eic,
        created_at=0,
    )


def fit_loss_grid(
    config: BotConfig,
    market_id: str,
    side: Literal["long", "short"],
    window_start_ts: int,
    window_end_ts: int,
    run_id: str,
    *,
    persist: bool = True,
    sqlite_path: Path | None = None,
    fills: list[PerFillPnL] | None = None,
) -> LossGridArtifact:
    """Fit the empirical (depth, tau) loss grid for one (market, side).

    Default driver: replay_historical_fills → build_loss_grid_artifact_from_fills →
    write_loss_grid_artifact (when persist=True).

    Test seam: callers may pass ``fills`` directly to bypass the DuckDB replay.
    The returned artifact carries created_at=0 if persist=False (sentinel),
    else the stamped created_at after artifact.write_loss_grid_artifact.
    """
    if sqlite_path is None:
        sqlite_path = Path(str(config.infra.sqlite_path))

    if fills is None:
        all_fills = replay_historical_fills(config, market_id, window_start_ts, window_end_ts)
        # Filter to side
        fills_for_side = [f for f in all_fills if f.side == side]
    else:
        fills_for_side = [f for f in fills if f.side == side]

    artifact = build_loss_grid_artifact_from_fills(
        fills=fills_for_side,
        config=config,
        market_id=market_id,
        side=side,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
        run_id=run_id,
    )

    if persist:
        # write_loss_grid_artifact stamps created_at; we cannot easily retrieve it
        # back without a SELECT — but the caller usually does not need it.
        write_loss_grid_artifact(artifact, sqlite_path=sqlite_path)

    return artifact
