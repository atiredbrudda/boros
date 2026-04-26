"""BACK-06: voluntary-cancel sensitivity. Two-row A/B on voluntary_cancel_forfeits_accumulated.

P0-01 RESOLVED 2026-04-23 (Boros official statement; flag default = False).
This sweep is a SANITY CHECK, not a blocker.

Divergence < voluntary_cancel_divergence_warn_pct (default 10%) -> sanity_check_pass.
Divergence >= 10% -> forfeit_branch_load_bearing flag — operator pursues opportunistic
contract-trace verification of P0-01. NOT an auto-ship-gate-fail.

[[backtest-voluntary-cancel-sensitivity-row]]
[[Voluntary cancel reward behavior]]
"""

from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Literal

import structlog

from ...config.schema import BotConfig
from ...manifest.schema import RunManifest
from ...manifest.writer import build_run_manifest
from ..replay import ReplayEngine
from ..schemas import BacktestRunOutput, ReplayConfig

log = structlog.get_logger(__name__)


async def run_forfeit_branch_sweep(
    base_run: ReplayConfig,
    *,
    parent_manifest: RunManifest,
    config: BotConfig,
) -> list[BacktestRunOutput]:
    """Run replay with voluntary_cancel_forfeits_accumulated in {False, True}.

    Returns exactly 2 rows: branch=benign (flag=False), branch=punitive (flag=True).
    Logs sanity_check_pass or forfeit_branch_load_bearing based on divergence.
    """
    rows: list[BacktestRunOutput] = []
    branches: list[tuple[Literal["benign", "punitive"], bool]] = [
        ("benign", False),
        ("punitive", True),
    ]
    for branch_name, flag_value in branches:
        child_config = config.model_copy(
            update={
                "strategy": config.strategy.model_copy(
                    update={
                        "voluntary_cancel_forfeits_accumulated": flag_value,
                    }
                ),
            }
        )
        child_manifest = build_run_manifest(child_config, parent_run_id=parent_manifest.run_id)
        cfg = replace(base_run, config=child_config, voluntary_cancel_branch=branch_name)
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
                    "sweep_axis": "forfeit_branch",
                    "sweep_value": branch_name,
                    "voluntary_cancel_branch": branch_name,
                    "parent_run_id": parent_manifest.run_id,
                }
            )
            rows.append(tagged)
        log.info(
            "backtest.sweep.forfeit_branch.row",
            branch=branch_name,
            flag=flag_value,
            child_run_id=child_manifest.run_id,
            annualized_pnl_pct=(result.rows[0].annualized_pnl_pct if result.rows else 0.0),
        )

    # Divergence check (BACK-06 sanity)
    benign_rows = [r for r in rows if r.voluntary_cancel_branch == "benign"]
    punitive_rows = [r for r in rows if r.voluntary_cancel_branch == "punitive"]
    if benign_rows and punitive_rows:
        benign_pnl = statistics.mean(r.annualized_pnl_pct for r in benign_rows)
        punitive_pnl = statistics.mean(r.annualized_pnl_pct for r in punitive_rows)
        divergence = abs(benign_pnl - punitive_pnl)
        threshold = float(config.backtest.voluntary_cancel_divergence_warn_pct)
        if divergence < threshold:
            log.info(
                "forfeit_branch.sanity_check_pass",
                divergence=divergence,
                threshold=threshold,
                note="P0-01 official-statement evidence intact; benign branch is the default.",
            )
        else:
            log.warning(
                "forfeit_branch_load_bearing",
                divergence=divergence,
                threshold=threshold,
                note=(
                    "EV formula sensitive to P0-01 (still official-statement, not "
                    "contract-traced). Operator: pursue opportunistic contract-trace "
                    "verification of cancelOrder() in pendle-finance/boros-core-public."
                ),
            )
    return rows


__all__ = ["run_forfeit_branch_sweep"]
