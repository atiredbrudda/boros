"""FILL-06: 15-min-cadence rolling refit loop.

Spawned from brain.main.run() alongside the existing heartbeat + ingest tasks.
Initial fit is synchronous (boot-block ~30s); subsequent fits are async-driven
at `config.fill_model.refit_cadence_s` (default 900s).

Per-loop errors are caught and logged; the loop continues. Mirrors
data/poller/markets_poller.run_markets_poller.

[[rolling-14-day-refit-cadence-and-staleness]]
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import polars as pl
import structlog

from ..config.schema import BotConfig
from ..data import chain_time
from .features import build_features_table
from .fit import fit_market_side

log = structlog.get_logger(__name__)

__all__ = ["refit_once", "run_fill_model_refit_loop"]

# Resolve project root from __file__ so the sqlite_path is always absolute regardless
# of the CWD at invocation time. This mirrors features.py and artifact.py conventions
# and prevents the write going to python/state/state.sqlite when the CLI process is
# launched from the python/ subdirectory. Phase 05.5 fix — same-database discipline.
_REFIT_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # boros_brain/fill_model → boros/


async def refit_once(
    config: BotConfig,
    run_id: str,
    *,
    current_chain_ts: int | None = None,
) -> None:
    """One refit across all (market_id, side) in config.markets.

    Uses `await chain_time.now_cached()` for the window end-timestamp per
    CLAUDE.md INFRA-14 (all time comparisons go through the chain_time cache —
    wall-clock is forbidden in brain/decision/data/screener/fill_model).

    Args:
        config: BotConfig
        run_id: ULID
        current_chain_ts: Optional chain_ts upper-bound for the fit window. None = live mode
            (uses chain_time.now_cached). Backtest replay MUST pass the current tick's
            chain_ts to prevent look-ahead bias (Bug C — Phase 05.4-03).
    """
    if not config.markets:
        log.info("fill_model.refit_skipped_no_markets", run_id=run_id)
        return

    if current_chain_ts is None:
        now_s = await chain_time.now_cached()
        window_end_ts = int(now_s)
    else:
        window_end_ts = int(current_chain_ts)

    window_start_ts = window_end_ts - int(config.fill_model.window_days * 86400)

    for mkt in config.markets:
        for side in ("long", "short"):
            try:
                # Step 1: build (or rebuild) the feature table
                fs = build_features_table(
                    config=config,
                    market_id=mkt.market_id,
                    window_start_ts=window_start_ts,
                    window_end_ts=window_end_ts,
                )
                # Step 2: load the parquet back into memory for the fit
                df = pl.read_parquet(fs.path)
                # Step 3: fit — use absolute sqlite_path (Phase 05.5 fix: relative path
                # resolves to python/state/state.sqlite when launched from python/ subdir,
                # not to boros/state/state.sqlite where predict() reads from). Pass
                # window_end_ts so degraded artifacts record correct fit_window_end_ts
                # (sentinel 0 → fit_age_s ~ 56 years >> fit_max_staleness_s=3600 → crash).
                sqlite_path_abs = _REFIT_PROJECT_ROOT / config.infra.sqlite_path
                fit_market_side(
                    features_df=df,
                    market_id=mkt.market_id,
                    side=side,  # type: ignore[arg-type]  # str → Literal["long","short"]
                    config=config,
                    run_id=run_id,
                    sqlite_path=sqlite_path_abs,
                    window_end_ts=window_end_ts,
                )
            except Exception as exc:  # noqa: BLE001 — do not halt brain on per-market fit failure
                log.exception(
                    "fill_model.refit_failed",
                    run_id=run_id,
                    market_id=mkt.market_id,
                    side=side,
                    err=str(exc),
                )


async def run_fill_model_refit_loop(config: BotConfig, run_id: str) -> None:
    """Long-running task. Pattern = markets_poller.run_markets_poller."""
    log.info("fill_model.refit_loop_started", run_id=run_id, cadence_s=config.fill_model.refit_cadence_s)
    while True:
        try:
            await refit_once(config, run_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("fill_model.refit_failed", run_id=run_id, err=str(exc))
        await asyncio.sleep(config.fill_model.refit_cadence_s)
