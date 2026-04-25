"""SAFE-04 — CloShiftBreaker: detect N-tick shift in CLO incentive range.

Fires when the CLO range boundaries shift by more than n_ticks between the two
most-recent clo_history snapshots. A significant CLO range shift means our
resting orders are now potentially outside the incentivized range.

A1xA3 compound risk (stay-out-of-range branch):
  When voluntary_cancel_forfeits_accumulated=True (punitive branch), re-posting
  after a CLO shift would forfeit sunk accumulated rewards from the old placement.
  In that case, the breaker emits CANCEL_ALL_HOLD_NO_REPLACE instead of
  CANCEL_ALL_AND_RECALIBRATE, so the coordinator holds without re-placing until
  the operator manually resets. This preserves the option to reclaim any earned
  rewards before cancelling.

  As of 2026-04-23, voluntary_cancel_forfeits_accumulated=False per Boros official
  team statement ([[Voluntary cancel reward behavior]]). The punitive branch is
  retained as dead-code fallback for Phase-5 backtest sensitivity runs.

Requirements:
  SAFE-04 — CLO shift predictive circuit breaker

Wiki reference:
  [[breaker-clo-removal-and-shift]]: SAFE-03 + SAFE-04 spec, tick conversion
  [[clo-shift-stay-out-of-range-branch]]: A1xA3 compound risk detail
  [[circuit-breakers-v05]]: full breaker taxonomy
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .base import Breaker, BreakerSignal
from ...state.writers.clo_history import read_clo_history_latest_n

log = structlog.get_logger(__name__)


class CloShiftBreaker(Breaker):
    """SAFE-04: Fire when CLO range shifts by > n_ticks between snapshots.

    Reads the two most-recent clo_history rows and computes the absolute
    difference in CLO boundaries. CLO threshold values are stored in tick units
    (integer-valued floats such as 9300.0, 9306.0), so the tick delta is the
    raw numeric difference: delta_ticks = |new_clo - old_clo|.

    Under voluntary_cancel_forfeits_accumulated=True (A1xA3 compound risk):
      Emits CANCEL_ALL_HOLD_NO_REPLACE — operator must manually reset before
      the coordinator re-places, because re-posting loses accumulated rewards.

    Under voluntary_cancel_forfeits_accumulated=False (confirmed default):
      Emits CANCEL_ALL_AND_RECALIBRATE — coordinator cancels and re-places at
      updated CLO range boundary.

    The breaker is stateless — hysteresis (min_re_arm_s) is owned by the
    BreakerCoordinator (Plan 04-06).
    """

    name = "clo_shift"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate CLO shift and return BreakerSignal.

        Parameters
        ----------
        sqlite_path : Path
            SQLite WAL DB path.
        w3 : Any
            AsyncWeb3 (unused by this breaker).
        parquet_root : Path
            Parquet root (unused by this breaker).
        config : BotConfig
            Frozen BotConfig; reads decision.breakers.clo_shift and markets[0].
        current_chain_ts : int
            Chain-time (seconds). NEVER use wall-clock inside check().

        Returns
        -------
        BreakerSignal
            tripped=True with reason 'clo_shifted' when |new_clo - old_clo| > n_ticks.
            kill_command_kind depends on voluntary_cancel_forfeits_accumulated flag:
              False (default) → CANCEL_ALL_AND_RECALIBRATE
              True  (punitive) → CANCEL_ALL_HOLD_NO_REPLACE (A1xA3 compound risk)
        """
        cfg = config.decision.breakers.clo_shift

        # Resolve rows: prefer market-scoped query when markets configured,
        # fall back to global-latest-2 when markets=[] (test convenience path).
        if config.markets:
            market_id = config.markets[0].market_id
            rows = read_clo_history_latest_n(sqlite_path, market_id, n=2)
        else:
            rows = _read_clo_latest_n_any(sqlite_path, n=2)

        if len(rows) < 2:
            log.debug(
                "clo_shift.insufficient_history",
                n=len(rows),
                market_id=market.market_id,
            )
            return BreakerSignal(tripped=False, reason="insufficient_history")

        # rows[0] is newest (DESC order), rows[1] is older
        new_row, old_row = rows[0], rows[1]

        # CLO threshold values are in tick units (integer-valued floats).
        # Tick delta = raw numeric difference (no scale multiplication needed).
        delta_lower_ticks = abs(new_row["clo_lower_thresh"] - old_row["clo_lower_thresh"])
        delta_upper_ticks = abs(new_row["clo_upper_thresh"] - old_row["clo_upper_thresh"])
        max_delta_ticks = max(delta_lower_ticks, delta_upper_ticks)

        if max_delta_ticks > cfg.n_ticks:
            payload = {
                "delta_ticks": float(max_delta_ticks),
                "delta_lower_ticks": float(delta_lower_ticks),
                "delta_upper_ticks": float(delta_upper_ticks),
            }

            # A1xA3 compound risk: punitive branch emits HOLD_NO_REPLACE.
            # Under voluntary_cancel_forfeits_accumulated=True, re-posting after
            # a CLO shift forfeits accumulated rewards from the old placement.
            # CANCEL_ALL_HOLD_NO_REPLACE prevents the coordinator from re-placing
            # until the operator manually assesses the trade-off.
            if config.strategy.voluntary_cancel_forfeits_accumulated:
                log.warning(
                    "clo_shift.tripped_punitive_branch",
                    max_delta_ticks=max_delta_ticks,
                    n_ticks=cfg.n_ticks,
                )
                return BreakerSignal(
                    tripped=True,
                    reason="clo_shifted",
                    payload=payload,
                    kill_command_kind="CANCEL_ALL_HOLD_NO_REPLACE",
                )

            log.warning(
                "clo_shift.tripped",
                max_delta_ticks=max_delta_ticks,
                n_ticks=cfg.n_ticks,
            )
            return BreakerSignal(
                tripped=True,
                reason="clo_shifted",
                payload=payload,
                kill_command_kind="CANCEL_ALL_AND_RECALIBRATE",
            )

        log.debug(
            "clo_shift.clo_stable",
            max_delta_ticks=max_delta_ticks,
            n_ticks=cfg.n_ticks,
        )
        return BreakerSignal(
            tripped=False,
            reason="clo_stable",
            payload={"delta_ticks": float(max_delta_ticks)},
        )


def _read_clo_latest_n_any(sqlite_path: Path, n: int = 2) -> list[dict[str, object]]:
    """Read the latest n clo_history rows without market_id filter.

    Used when no markets are configured in BotConfig (test convenience path).
    Production always has markets configured so this path is not taken in prod.
    """
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        rows = conn.execute(
            "SELECT snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw "
            "FROM clo_history ORDER BY snapshot_ts DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "snapshot_ts": r[0],
            "market_id": r[1],
            "clo_lower_thresh": r[2],
            "clo_upper_thresh": r[3],
            "f_index_raw": r[4],
        }
        for r in rows
    ]


__all__ = ["CloShiftBreaker"]
