"""BACK-03: cancel-latency sweep. Fixed grid L ∈ {0.5, 1, 2, 3, 5, 10}s by default.

Each child run gets a fresh RUN_MANIFEST with parent_run_id=base.run_id (PROTO-01).
A single manifest covering all sweep children would be a D2 pitfall (RESEARCH.md L485).

Expected sign: dP&L/dL < 0 (more latency = more inventory exposure on fills = worse P&L).
Non-monotonic curve → unexpected_monotonicity anomaly log.

[[backtest-cancel-latency-sweep]]
[[backtest-cancel-latency-two-axis]]
"""

from __future__ import annotations

from dataclasses import replace

import structlog

from ...config.schema import BotConfig
from ...manifest.schema import RunManifest
from ...manifest.writer import build_run_manifest
from ..replay import ReplayEngine
from ..schemas import BacktestRunOutput, ReplayConfig

log = structlog.get_logger(__name__)


async def run_cancel_latency_sweep(
    base_run: ReplayConfig,
    *,
    parent_manifest: RunManifest,
    config: BotConfig,
) -> list[BacktestRunOutput]:
    """Per BACK-03: deterministic 6-point grid (operator-overridable).

    Each child run gets a fresh manifest with parent_run_id=base.run_id.
    """
    rows: list[BacktestRunOutput] = []
    grid = list(config.backtest.cancel_latency_grid)
    for L in grid:
        child_manifest = build_run_manifest(config, parent_run_id=parent_manifest.run_id)
        cfg = replace(base_run, cancel_latency_s=float(L))
        engine = ReplayEngine(
            config=cfg.config,
            market_id=cfg.market_id,
            side=cfg.side,
            parquet_root=cfg.parquet_root,
            sqlite_path=cfg.sqlite_path,
            cancel_latency_s=cfg.cancel_latency_s,
            voluntary_cancel_branch=cfg.voluntary_cancel_branch,
            sigma_others_multiplier=cfg.sigma_others_multiplier,
            run_id=child_manifest.run_id,
            manifest=child_manifest,
        )
        result = await engine.run(seed_from_config=True)
        # Tag the child run's first row with this sweep axis + value
        for r in result.rows:
            tagged = r.model_copy(
                update={
                    "sweep_axis": "cancel_latency",
                    "sweep_value": float(L),
                    "parent_run_id": parent_manifest.run_id,
                }
            )
            rows.append(tagged)
        log.info(
            "backtest.sweep.cancel_latency.row",
            L=float(L),
            child_run_id=child_manifest.run_id,
            annualized_pnl_pct=(result.rows[0].annualized_pnl_pct if result.rows else 0.0),
        )
    _check_monotonicity(rows)
    return rows


def compute_dpnl_dl(rows: list[BacktestRunOutput]) -> list[tuple[float, float]]:
    """Central finite-difference of dP&L/dL on the sorted L grid.

    Returns [(L_i, slope_at_L_i), ...]. Endpoints use one-sided differences.
    """
    sorted_rows = sorted(
        [r for r in rows if r.sweep_axis == "cancel_latency"],
        key=lambda r: float(r.sweep_value),
    )
    n = len(sorted_rows)
    if n < 2:
        return []
    out: list[tuple[float, float]] = []
    for i in range(n):
        if i == 0:
            # Forward difference
            dL = float(sorted_rows[i + 1].sweep_value) - float(sorted_rows[i].sweep_value)
            dP = sorted_rows[i + 1].annualized_pnl_pct - sorted_rows[i].annualized_pnl_pct
        elif i == n - 1:
            # Backward difference
            dL = float(sorted_rows[i].sweep_value) - float(sorted_rows[i - 1].sweep_value)
            dP = sorted_rows[i].annualized_pnl_pct - sorted_rows[i - 1].annualized_pnl_pct
        else:
            # Central difference
            dL = float(sorted_rows[i + 1].sweep_value) - float(sorted_rows[i - 1].sweep_value)
            dP = sorted_rows[i + 1].annualized_pnl_pct - sorted_rows[i - 1].annualized_pnl_pct
        slope = dP / dL if dL != 0 else 0.0
        out.append((float(sorted_rows[i].sweep_value), slope))
    return out


def _check_monotonicity(rows: list[BacktestRunOutput]) -> None:
    """Emit unexpected_monotonicity anomaly if dP&L/dL is not monotone-decreasing."""
    sorted_rows = sorted(
        [r for r in rows if r.sweep_axis == "cancel_latency"],
        key=lambda r: float(r.sweep_value),
    )
    pnls = [r.annualized_pnl_pct for r in sorted_rows]
    # Expected: monotone-decreasing (more L = less P&L)
    for i in range(1, len(pnls)):
        if pnls[i] > pnls[i - 1]:
            log.warning(
                "backtest.sweep.cancel_latency.unexpected_monotonicity",
                L_lower=float(sorted_rows[i - 1].sweep_value),
                L_higher=float(sorted_rows[i].sweep_value),
                pnl_at_lower=pnls[i - 1],
                pnl_at_higher=pnls[i],
            )
            break  # one warning per sweep is enough


__all__ = ["run_cancel_latency_sweep", "compute_dpnl_dl"]
