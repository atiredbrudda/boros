"""SAFE-02 — OracleStaleBreaker: fIndex oracle staleness check.

Fires when the fIndex oracle's last update time (fTime) is older than
fraction_of_max × maxUpdateDelay. Default fraction is 0.7 (70%) so the
breaker fires predictively before the protocol considers the oracle stale.

This is an early-warning design: if we fire at 70% of the max allowed delay,
we have 30% of the delay budget remaining to cancel orders before the protocol
acts. Reactive-only checks (at 100% threshold) leave no buffer.

Requirements:
  SAFE-02 — oracle staleness predictive circuit breaker

Wiki reference:
  [[breaker-oracle-stale]]: spec, 0.7 × maxUpdateDelay early-fire discipline
  [[circuit-breakers-v05]]: full breaker taxonomy
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .base import Breaker, BreakerSignal

log = structlog.get_logger(__name__)


class OracleStaleBreaker(Breaker):
    """SAFE-02: Fire when oracle fTime age exceeds fraction_of_max * maxUpdateDelay.

    The check() method accepts optional f_time and max_update_delay keyword
    overrides for test injection (avoids requiring a live RPC call in tests).
    In production, these are read from the fIndexOracle contract via w3.

    The breaker is stateless — hysteresis (min_re_arm_s) is owned by the
    BreakerCoordinator (Plan 04-06).
    """

    name = "oracle_stale"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
        # Optional overrides for testing (avoids real RPC in unit tests)
        f_time: int | None = None,
        max_update_delay: int | None = None,
    ) -> BreakerSignal:
        """Evaluate oracle staleness and return BreakerSignal.

        Parameters
        ----------
        sqlite_path : Path
            SQLite WAL DB path (unused by this breaker directly).
        w3 : Any
            AsyncWeb3 instance. Used to read fIndex if f_time override not given.
            If w3 is None AND f_time override is None, returns tripped=False with
            reason='no_w3_yet' (non-blocking: breaker waits for RPC to be ready).
        parquet_root : Path
            Parquet root (unused by this breaker).
        config : BotConfig
            Frozen BotConfig; reads decision.breakers.oracle_stale and markets[0].
        current_chain_ts : int
            Chain-time (seconds). NEVER use wall-clock inside check() —
            no_time_time_lint.py enforces this.
        f_time : int | None
            Optional override: fIndex oracle last-update timestamp (seconds).
            If given, skips the RPC call. Used by unit tests.
        max_update_delay : int | None
            Optional override: oracle maxUpdateDelay (seconds).
            If given, skips reading from config.markets[0].max_update_delay_s.
            Used by unit tests that don't configure markets list.

        Returns
        -------
        BreakerSignal
            tripped=True with reason 'oracle_stale' and kill_command_kind='CANCEL_ALL'
            when age_s > fraction_of_max * max_update_delay_s.
        """
        cfg = config.decision.breakers.oracle_stale

        # Resolve f_time: prefer explicit override, then RPC call
        if f_time is None:
            if w3 is None:
                log.debug("oracle_stale.no_w3_yet")
                return BreakerSignal(tripped=False, reason="no_w3_yet")

            # Read from on-chain oracle
            if not config.markets:
                log.debug("oracle_stale.no_markets_configured")
                return BreakerSignal(tripped=False, reason="no_markets_configured")

            market = config.markets[0]
            try:
                from ...data.findex_reader import FIndexReader

                reader = FIndexReader(w3=w3, oracle_address=market.fIndex_oracle_address)
                result = await reader.get_latest_fIndex()
                f_time_val = result["fTime"]
            except Exception as exc:
                log.warning("oracle_stale.read_failed", err=str(exc))
                return BreakerSignal(tripped=False, reason="read_failed")
        else:
            f_time_val = f_time

        # Resolve max_update_delay: prefer explicit override, then config
        if max_update_delay is None:
            if not config.markets:
                log.debug("oracle_stale.no_markets_for_delay")
                return BreakerSignal(tripped=False, reason="no_markets_for_delay")
            max_delay = config.markets[0].max_update_delay_s
        else:
            max_delay = max_update_delay

        age_s = current_chain_ts - f_time_val
        threshold_s = cfg.fraction_of_max * max_delay

        if age_s > threshold_s:
            log.warning(
                "oracle_stale.tripped",
                age_s=age_s,
                threshold_s=threshold_s,
                max_delay=max_delay,
                fraction_of_max=cfg.fraction_of_max,
            )
            return BreakerSignal(
                tripped=True,
                reason="oracle_stale",
                payload={
                    "f_time": f_time_val,
                    "age_s": age_s,
                    "threshold_s": threshold_s,
                },
                kill_command_kind="CANCEL_ALL",
            )

        log.debug(
            "oracle_stale.fresh",
            age_s=age_s,
            threshold_s=threshold_s,
        )
        return BreakerSignal(
            tripped=False,
            reason="fresh",
            payload={"age_s": age_s, "threshold_s": threshold_s},
        )


__all__ = ["OracleStaleBreaker"]
