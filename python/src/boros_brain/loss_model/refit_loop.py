"""LOSS-01/02: 15-min-cadence rolling loss-grid refit loop.

Spawned from brain.main.run() alongside the existing fill_model refit loop.
Initial fit is synchronous (boot-block, same pattern as fill_model.refit_once).
Subsequent fits are async-driven at _get_loss_model_config(config).refit_cadence_s (default 900s).

Per-loop errors are caught and logged; the loop continues. Mirrors
fill_model.refit_loop.run_fill_model_refit_loop.

[[empirical-loss-grid-v05]]: window_days = 90 (longer than fill_model — fills are rarer).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..data import chain_time
from .config import LossModelConfig
from .fit import fit_loss_grid

log = structlog.get_logger(__name__)

__all__ = ["refit_once", "run_loss_model_refit_loop"]


def _get_loss_model_config(config: BotConfig) -> LossModelConfig:
    """Plan-03-01-independent fallback until Plan 03-02 wires BotConfig.loss_model."""
    return getattr(config, "loss_model", None) or LossModelConfig()


async def refit_once(
    config: BotConfig,
    run_id: str,
    *,
    current_chain_ts: int | None = None,
) -> None:
    """One refit across all (market_id, side) in config.markets.

    Uses ``await chain_time.now_cached()`` for the window end-timestamp per
    CLAUDE.md INFRA-14 — wall-clock is forbidden in loss_model/ (lint extension
    lands in Plan 03-04; pre-emptive discipline).

    Args:
        config: BotConfig
        run_id: ULID
        current_chain_ts: Optional chain_ts upper-bound for the fit window. None = live mode
            (uses chain_time.now_cached). Backtest replay would pass the current tick's
            chain_ts to prevent look-ahead bias — Phase 05.5-02 mirror of d954bc5
            (fill_model.refit_once Phase 05.4-03 Bug C). The backtest engine does NOT
            currently invoke loss_model.refit_once (loss_model is live-mode-only today;
            backtest uses the expected_loss read path with stored grids), but this
            kwarg is wired now to preserve write-side discipline for future backtest
            invocations and to prevent live-mode clock-rollback from poisoning
            ``state.loss_grid_artifacts`` with future-dated window_end_ts.
            See [[loss-model-expected-loss-look-ahead-read-path]].
    """
    if not config.markets:
        log.info("loss_model.refit_skipped_no_markets", run_id=run_id)
        return

    if current_chain_ts is None:
        now_s = await chain_time.now_cached()
        window_end_ts = int(now_s)
    else:
        window_end_ts = int(current_chain_ts)
    window_start_ts = window_end_ts - int(_get_loss_model_config(config).window_days * 86400)

    sqlite_path = Path(str(config.infra.sqlite_path))
    for mkt in config.markets:
        for side in ("long", "short"):
            try:
                fit_loss_grid(
                    config,
                    mkt.market_id,
                    side,  # type: ignore[arg-type]
                    window_start_ts,
                    window_end_ts,
                    run_id,
                    sqlite_path=sqlite_path,
                )
            except Exception as exc:  # noqa: BLE001 — never halt brain on per-market failure
                log.exception(
                    "loss_model.refit_failed",
                    run_id=run_id,
                    market_id=mkt.market_id,
                    side=side,
                    err=str(exc),
                )


async def run_loss_model_refit_loop(config: BotConfig, run_id: str) -> None:
    """Long-running task. Pattern = fill_model.refit_loop.run_fill_model_refit_loop."""
    log.info(
        "loss_model.refit_loop_started",
        run_id=run_id,
        cadence_s=_get_loss_model_config(config).refit_cadence_s,
    )
    while True:
        try:
            await refit_once(config, run_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("loss_model.refit_failed", run_id=run_id, err=str(exc))
        await asyncio.sleep(_get_loss_model_config(config).refit_cadence_s)
