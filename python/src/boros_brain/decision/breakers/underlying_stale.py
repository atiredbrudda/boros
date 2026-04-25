"""SAFE-09 — UnderlyingStaleBreaker: underlying_apr feed older than 2× expected cadence.

Detects when the underlying rate feed parquet data has not been updated within
the expected window for its exchange. Stale underlying data invalidates the
basis model (E[loss|fill] integral relies on current implied-underlying spread).

Trip condition: age_s > 2 × expected_cadence_s_per_exchange[exchange]

Exchange cadence defaults (operator-tunable via BotConfig):
  binance     = 28800s (8h)
  okx         = 3600s  (1h)
  hyperliquid = 60s    (1min)

See [[underlying-apr-cadence-by-exchange]] for cadence justification.

STRIDE: T-04-05-04 — DuckDB conn opened per call (~1ms); bounded to one
exchange/symbol parquet partition.

[[breaker-underlying-feed-stale]]: SAFE-09 spec, A7 absorbed
[[underlying-apr-cadence-by-exchange]]: cadence table by exchange
[[circuit-breakers-v05]]: breaker taxonomy + routing
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Breaker, BreakerSignal
from ...data.underlying_apr_reader import read_underlying_apr_max_ts

__all__ = ["UnderlyingStaleBreaker"]


class UnderlyingStaleBreaker(Breaker):
    """SAFE-09: fires when underlying_apr parquet data is older than 2× expected cadence.

    expected_cadence_s is looked up by market.underlying_exchange from
    BotConfig.decision.breakers.underlying_stale.expected_cadence_s_per_exchange.
    If the exchange is not in the dict, the breaker stays silent (no cadence = no gate).
    """

    name = "underlying_stale"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate SAFE-09 underlying feed staleness condition."""
        cfg = config.decision.breakers.underlying_stale
        market = config.markets[0]

        expected_cadence_s = cfg.expected_cadence_s_per_exchange.get(
            market.underlying_exchange
        )
        if expected_cadence_s is None:
            return BreakerSignal(
                tripped=False,
                reason=f"no_cadence_for_exchange_{market.underlying_exchange}",
            )

        last_ts = read_underlying_apr_max_ts(
            parquet_root, market.underlying_exchange, market.underlying_symbol
        )
        if last_ts is None:
            return BreakerSignal(tripped=False, reason="no_parquet_data_yet")

        age_s = current_chain_ts - last_ts

        if age_s > 2 * expected_cadence_s:
            return BreakerSignal(
                tripped=True,
                reason="underlying_feed_stale",
                payload={
                    "age_s": age_s,
                    "expected_cadence_s": expected_cadence_s,
                    "exchange": market.underlying_exchange,
                    "symbol": market.underlying_symbol,
                },
                kill_command_kind="HALT_AND_ALERT",
            )

        return BreakerSignal(
            tripped=False,
            reason="fresh",
            payload={
                "age_s": age_s,
                "expected_cadence_s": expected_cadence_s,
            },
        )
