"""SAFE-05 — FillRateBreaker: detect runaway fill accumulation.

Fires when the number of confirmed fills in the last 60 minutes exceeds
k_fills_per_hour. Fills are bad — a fill means our limit order was taken,
triggering forced market-close (accept taker fee as insurance). Runaway
fills signal that placement has drifted into the active market range.

PAUSE_AND_ALERT is non-self-clearing: once fired, the breaker stays active
until the operator manually resets it via the reset-breaker CLI subcommand
(Plan 04-06). This prevents the coordinator from automatically re-placing
orders into a market that is clearly taking fills at an abnormal rate.

Requirements:
  SAFE-05 — fill-rate runaway predictive circuit breaker

Wiki reference:
  [[breaker-fill-rate-runaway]]: spec, PAUSE_AND_ALERT non-self-clearing semantics
  [[circuit-breakers-v05]]: full breaker taxonomy
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .base import Breaker, BreakerSignal
from ...state.writers.tx_receipts import read_tx_receipts_fill_count

log = structlog.get_logger(__name__)


class FillRateBreaker(Breaker):
    """SAFE-05: Fire when confirmed fills in the last hour exceed k_fills_per_hour.

    Reads tx_receipts with event_type='fill' within the last 3600 seconds and
    counts them. If the count exceeds k_fills_per_hour, emits PAUSE_AND_ALERT.

    Note: PAUSE_AND_ALERT is non-self-clearing. The operator must use the
    reset-breaker CLI subcommand (Plan 04-06) to resume normal operation
    after investigating why fills are accumulating.

    Note on pre-migration rows: tx_receipts rows inserted before migration 0007
    have event_type='unknown' (server_default). The query filters by event_type='fill'
    only, so pre-migration rows are excluded (conservative under-counting —
    preferable to over-firing the breaker on stale data).

    The breaker is stateless — hysteresis (min_re_arm_s) is owned by the
    BreakerCoordinator (Plan 04-06).
    """

    name = "fill_rate"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate fill-rate runaway and return BreakerSignal.

        Parameters
        ----------
        sqlite_path : Path
            SQLite WAL DB path.
        w3 : Any
            AsyncWeb3 (unused by this breaker).
        parquet_root : Path
            Parquet root (unused by this breaker).
        config : BotConfig
            Frozen BotConfig; reads decision.breakers.fill_rate and markets[0].
        current_chain_ts : int
            Chain-time (seconds). NEVER use wall-clock inside check() —
            no_time_time_lint.py enforces this.

        Returns
        -------
        BreakerSignal
            tripped=True with reason 'fill_rate_runaway' and
            kill_command_kind='PAUSE_AND_ALERT' when n_fills > k_fills_per_hour.
        """
        cfg = config.decision.breakers.fill_rate
        market_id: str | None = config.markets[0].market_id if config.markets else None

        one_hour_ago = current_chain_ts - 3600

        n_fills = read_tx_receipts_fill_count(
            sqlite_path,
            market_id=market_id,
            since_ts=one_hour_ago,
        )

        if n_fills > cfg.k_fills_per_hour:
            log.warning(
                "fill_rate.runaway",
                n_fills_last_hour=n_fills,
                k_fills_per_hour=cfg.k_fills_per_hour,
                market_id=market_id,
            )
            return BreakerSignal(
                tripped=True,
                reason="fill_rate_runaway",
                payload={
                    "n_fills_last_hour": n_fills,
                    "threshold": cfg.k_fills_per_hour,
                },
                kill_command_kind="PAUSE_AND_ALERT",
            )

        log.debug(
            "fill_rate.ok",
            n_fills_last_hour=n_fills,
            k_fills_per_hour=cfg.k_fills_per_hour,
        )
        return BreakerSignal(
            tripped=False,
            reason="ok",
            payload={"n_fills_last_hour": n_fills},
        )


__all__ = ["FillRateBreaker"]
