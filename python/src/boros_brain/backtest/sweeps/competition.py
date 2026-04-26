"""BACK-04: competition sweep. Multiplier m on sigma_others per replay window.

For each m in config.backtest.competition_multipliers (default {0.5, 0.75, 1.0, 1.5, 2.0, 3.0}),
substitute Σ_others' = m × Σ_others_observed at the replay's r_capped_curve input.
m=1.0 is the unperturbed baseline.

The substitution does NOT alter trade tape — that would require a full second-order
simulation of competing bots' behavior, which is out of scope.

Expected sign: dP&L/dm < 0 (more competition = smaller share = worse P&L).

[[backtest-competition-sweep]]
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


async def run_competition_sweep(
    base_run: ReplayConfig,
    *,
    parent_manifest: RunManifest,
    config: BotConfig,
) -> list[BacktestRunOutput]:
    """Per BACK-04: multiplier sweep on sigma_others; m=1.0 is the unperturbed baseline."""
    rows: list[BacktestRunOutput] = []
    grid = list(config.backtest.competition_multipliers)
    for m in grid:
        child_manifest = build_run_manifest(config, parent_run_id=parent_manifest.run_id)
        cfg = replace(base_run, sigma_others_multiplier=float(m))
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
        result = await engine.run()
        for r in result.rows:
            tagged = r.model_copy(
                update={
                    "sweep_axis": "competition",
                    "sweep_value": float(m),
                    "parent_run_id": parent_manifest.run_id,
                }
            )
            rows.append(tagged)
        log.info(
            "backtest.sweep.competition.row",
            m=float(m),
            child_run_id=child_manifest.run_id,
            annualized_pnl_pct=(result.rows[0].annualized_pnl_pct if result.rows else 0.0),
        )
    _check_monotonicity(rows)
    return rows


def compute_dpnl_dq(rows: list[BacktestRunOutput]) -> list[tuple[float, float]]:
    """Central finite-difference of dP&L/dm on the sorted m grid."""
    sorted_rows = sorted(
        [r for r in rows if r.sweep_axis == "competition"],
        key=lambda r: float(r.sweep_value),
    )
    n = len(sorted_rows)
    if n < 2:
        return []
    out: list[tuple[float, float]] = []
    for i in range(n):
        if i == 0:
            dm = float(sorted_rows[i + 1].sweep_value) - float(sorted_rows[i].sweep_value)
            dP = sorted_rows[i + 1].annualized_pnl_pct - sorted_rows[i].annualized_pnl_pct
        elif i == n - 1:
            dm = float(sorted_rows[i].sweep_value) - float(sorted_rows[i - 1].sweep_value)
            dP = sorted_rows[i].annualized_pnl_pct - sorted_rows[i - 1].annualized_pnl_pct
        else:
            dm = float(sorted_rows[i + 1].sweep_value) - float(sorted_rows[i - 1].sweep_value)
            dP = sorted_rows[i + 1].annualized_pnl_pct - sorted_rows[i - 1].annualized_pnl_pct
        slope = dP / dm if dm != 0 else 0.0
        out.append((float(sorted_rows[i].sweep_value), slope))
    return out


def _check_monotonicity(rows: list[BacktestRunOutput]) -> None:
    """Emit unexpected_monotonicity anomaly if dP&L/dm is not monotone-decreasing."""
    sorted_rows = sorted(
        [r for r in rows if r.sweep_axis == "competition"],
        key=lambda r: float(r.sweep_value),
    )
    pnls = [r.annualized_pnl_pct for r in sorted_rows]
    for i in range(1, len(pnls)):
        if pnls[i] > pnls[i - 1]:
            log.warning(
                "backtest.sweep.competition.unexpected_monotonicity",
                m_lower=float(sorted_rows[i - 1].sweep_value),
                m_higher=float(sorted_rows[i].sweep_value),
                pnl_at_lower=pnls[i - 1],
                pnl_at_higher=pnls[i],
            )
            break


__all__ = ["run_competition_sweep", "compute_dpnl_dq"]
