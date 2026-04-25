"""SAFE-03 — CloRemovalBreaker: detect when CLO incentive range has been removed.

Fires when either clo_lower_thresh or clo_upper_thresh is 0.0 in the most-recent
clo_history snapshot. A market with CLO thresholds of zero is no longer incentivized —
any active position earns no Limit Order Liquidity Rewards and should be cancelled
before the rewards epoch processes.

Requirements:
  SAFE-03 — CLO removal predictive circuit breaker

Wiki reference:
  [[breaker-clo-removal-and-shift]]: SAFE-03 + SAFE-04 spec, tick conversion
  [[circuit-breakers-v05]]: full breaker taxonomy
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .base import Breaker, BreakerSignal
from ...state.writers.clo_history import read_latest_clo_history

log = structlog.get_logger(__name__)


class CloRemovalBreaker(Breaker):
    """SAFE-03: Fire when CLO incentive range boundaries drop to zero.

    Reads the latest clo_history row for the active market. If clo_lower_thresh
    or clo_upper_thresh is 0.0, the market's CLO program has been removed —
    emits CANCEL_ALL_AND_ALERT.

    When config.markets is empty (e.g. in tests), reads the globally latest
    clo_history row (no market_id filter). This allows the breaker to function
    correctly in test environments without a fully configured markets list.

    The breaker is stateless — hysteresis (min_re_arm_s) is owned by the
    BreakerCoordinator (Plan 04-06).
    """

    name = "clo_removal"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate CLO removal and return BreakerSignal.

        Parameters
        ----------
        sqlite_path : Path
            SQLite WAL DB path.
        w3 : Any
            AsyncWeb3 (unused by this breaker).
        parquet_root : Path
            Parquet root (unused by this breaker).
        config : BotConfig
            Frozen BotConfig; reads markets[0].market_id if available.
        current_chain_ts : int
            Chain-time (seconds). NEVER use wall-clock inside check().

        Returns
        -------
        BreakerSignal
            tripped=True with reason 'clo_removed' and kill_command_kind='CANCEL_ALL_AND_ALERT'
            when either CLO threshold is 0.0.
        """
        # Resolve market_id: use config market if available, else read any latest row.
        market_id: str | None = None
        if config.markets:
            market_id = config.markets[0].market_id

        if market_id is not None:
            row = read_latest_clo_history(sqlite_path, market_id)
        else:
            # No market configured: read the globally latest row (test convenience path).
            # Production always has markets configured — this path is for test environments.
            row = _read_latest_clo_any(sqlite_path)

        if row is None:
            log.debug("clo_removal.no_clo_history_yet", market_id=market_id)
            return BreakerSignal(tripped=False, reason="no_clo_history_yet")

        clo_lower = row["clo_lower_thresh"]
        clo_upper = row["clo_upper_thresh"]

        if clo_lower == 0.0 or clo_upper == 0.0:
            log.warning(
                "clo_removal.tripped",
                market_id=row.get("market_id"),
                clo_lower=clo_lower,
                clo_upper=clo_upper,
            )
            return BreakerSignal(
                tripped=True,
                reason="clo_removed",
                payload={"clo_lower": clo_lower, "clo_upper": clo_upper},
                kill_command_kind="CANCEL_ALL_AND_ALERT",
            )

        log.debug(
            "clo_removal.clo_present",
            market_id=row.get("market_id"),
            clo_lower=clo_lower,
            clo_upper=clo_upper,
        )
        return BreakerSignal(tripped=False, reason="clo_present")


def _read_latest_clo_any(sqlite_path: Path) -> dict[str, object] | None:
    """Read the globally latest clo_history row (no market_id filter).

    Used when no markets are configured in BotConfig (test convenience path).
    Production always has markets configured so this path is not taken in prod.
    """
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            "SELECT snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw "
            "FROM clo_history ORDER BY snapshot_ts DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "snapshot_ts": row[0],
        "market_id": row[1],
        "clo_lower_thresh": row[2],
        "clo_upper_thresh": row[3],
        "f_index_raw": row[4],
    }


__all__ = ["CloRemovalBreaker"]
