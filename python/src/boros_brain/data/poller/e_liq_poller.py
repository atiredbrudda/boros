"""DATA-11 — Live E_liq poller writing to reward_budget_history.

Polls GET /markets every `e_liq_poll_interval_s` (default 5s, range 1-5s per
DataConfig) and writes one `reward_budget_history` row per market per cycle.

**Anti-pattern 4 guard (ARCHITECTURE.md §9 / PITFALLS §A2):**
NO cross-poll caching. `E_liq_per_epoch` rebalances dynamically per epoch;
a stale cache produces wrong `R_apr_on_collateral` in DATA-09. Every call to
`run_one_cycle()` writes a fresh row regardless of whether the value changed.

**T-01-10-03 (backoff on 5xx):**
`_get_with_backoff()` wraps `get_markets()` with exponential backoff delays
[0.5, 1, 2, 4, 8s]. On 5 consecutive failures across a single cycle:
- Log ERROR with `fail_count`
- Publish `poller.e_liq.degraded` ZMQ event (if fail_count >= 5)
- Return without writing any rows (do NOT crash — dead poller < dead brain)
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Protocol, runtime_checkable

import structlog

from boros_brain.data.chain_time import now_cached as get_chain_time_cached
from boros_brain.state.writers.reward_budget_history import insert_reward_budget_row

log = structlog.get_logger(__name__)

# Backoff delays in seconds: [0.5, 1, 2, 4, 8] — five retry windows.
_BACKOFF_DELAYS = [0.5, 1.0, 2.0, 4.0, 8.0]


@runtime_checkable
class _RestClient(Protocol):
    async def get_markets(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class _EventPub(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...


class ELiqPoller:
    """DATA-11: polls GET /markets every e_liq_poll_interval_s and writes one
    reward_budget_history row per market per cycle. NO CACHE per PITFALLS §A2.

    Parameters
    ----------
    config:
        Live BotConfig. Reads `data.e_liq_poll_interval_s`, `markets`.
    conn:
        SQLite WAL connection (WAL mode, brain-owned).
    rest:
        Object with `async get_markets() -> list[dict]` (BorosRestClient or stub).
    run_id:
        Active run_id for traceability in reward_budget_history rows.
    event_pub:
        Object with `async publish(topic: str, payload: dict)`.
        Used to emit `poller.e_liq.degraded` after 5 consecutive failures.
    """

    def __init__(
        self,
        config: Any,
        conn: sqlite3.Connection,
        rest: Any,
        run_id: str,
        event_pub: Any,
    ) -> None:
        self.interval: float = config.data.e_liq_poll_interval_s
        self.markets: list[str] = [m.market_id for m in config.markets]
        self.conn = conn
        self.rest = rest
        self.run_id = run_id
        self.event_pub = event_pub
        self._fail_count: int = 0

    async def run_one_cycle(self) -> None:
        """Run one polling cycle: fetch markets, write one row per in-scope market.

        On fetch failure after all retries: log ERROR, publish degraded event when
        _fail_count >= 5, and return without writing rows. Does not raise.
        Each individual retry attempt (inside _get_with_backoff) increments _fail_count.
        """
        try:
            markets = await self._get_with_backoff()
        except Exception as exc:
            log.error(
                "e_liq_poller.fetch_failed",
                error=str(exc),
                fail_count=self._fail_count,
            )
            if self._fail_count >= 5:
                await self.event_pub.publish(
                    "poller.e_liq.degraded",
                    {"fail_count": self._fail_count},
                )
            return

        self._fail_count = 0
        chain_ts = await get_chain_time_cached()

        for m in markets:
            if m.get("marketId") not in self.markets:
                continue
            # Field names per Assumption A5 from 01-RESEARCH.md.
            # Reconcile with live /markets response in Wave-0 spike.
            insert_reward_budget_row(
                self.conn,
                market_id=m["marketId"],
                e_liq_per_epoch=float(m["liquidityRewardPerEpoch"]),
                long_budget=float(m["longBudget"]),
                short_budget=float(m["shortBudget"]),
                chain_ts=chain_ts,
                run_id=self.run_id,
                data_source="polled",
            )
            log.info(
                "e_liq_poller.row_written",
                market_id=m["marketId"],
                e_liq_per_epoch=float(m["liquidityRewardPerEpoch"]),
                chain_ts=chain_ts,
            )

    async def _get_with_backoff(self) -> list[dict[str, Any]]:
        """Fetch markets with exponential backoff on failure.

        Delays: [0.5, 1, 2, 4, 8] seconds (5 retries). Each failed attempt
        increments `self._fail_count` so that the degraded-event threshold
        (>= 5) fires after one exhausted-retry cycle when all 5 attempts fail.
        Raises the last exception if all retries fail.
        """
        last_exc: BaseException | None = None
        for delay in _BACKOFF_DELAYS:
            try:
                result: list[dict[str, Any]] = await self.rest.get_markets()
                # Successful fetch — reset _fail_count handled by run_one_cycle.
                return result
            except Exception as exc:
                last_exc = exc
                self._fail_count += 1
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def loop(self) -> None:
        """Continuous polling loop — runs until cancelled."""
        while True:
            await self.run_one_cycle()
            await asyncio.sleep(self.interval)
