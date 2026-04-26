"""DATA-13 — 1 Hz margin poller. POST /accounts/get-net-margin → state.margin_history.

Mirrors ELiqPoller (data/poller/e_liq_poller.py) exactly. Backoff on failure:
[0.5, 1, 2, 4, 8] seconds. Degraded event 'poller.margin.degraded' published
after 5 consecutive failures.

SAFE-01 data source: POST /accounts/get-net-margin returns per-account aggregate
margin data. The poller fans out one margin_history row per market_id in the
active market list for query convenience (each row carries the same USD values —
the market_id dimension is for the MarginTrajectoryBreaker query pattern).

Assumption A1 (RESEARCH.md): the actual field shape in the response JSON is
  {"netMargin": <float, USD>, "maintenanceMargin": <float, USD>,
   "availableCollateral": <float, USD>}
This is ASSUMED — verified in Plan 04-04 SAFE-01 test stage with stubbed response.
If the live API returns different field names, update _parse_margin_response()
and the wiki page [[boros-rest-api-margin-endpoint]] in the same commit.

no_time_time_lint.py: `python/src/boros_brain/data/` is in PROTECTED_DIRS — no
wall-clock calls are permitted here. Use get_chain_time_cached() for timestamps.

[[boros-rest-api-margin-endpoint]]: endpoint contract + assumed field shape
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Protocol, runtime_checkable

import structlog

from boros_brain.data.chain_time import now_cached as get_chain_time_cached
from boros_brain.state.writers.margin_history import insert_margin_snapshot

log = structlog.get_logger(__name__)

# Backoff delays in seconds: [0.5, 1, 2, 4, 8] — five retry windows.
_BACKOFF_DELAYS = [0.5, 1.0, 2.0, 4.0, 8.0]


@runtime_checkable
class _RestClient(Protocol):
    async def post_get_net_margin(self, account_id: int) -> dict[str, Any]: ...


@runtime_checkable
class _EventPub(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...


def _parse_margin_response(resp: dict[str, Any]) -> tuple[float, float, float]:
    """Extract (net_margin_usd, maintenance_margin_usd, available_collateral_usd).

    Assumption A1 field names. Update this function + wiki page if live API differs.
    """
    return (
        float(resp.get("netMargin", 0.0)),
        float(resp.get("maintenanceMargin", 0.0)),
        float(resp.get("availableCollateral", 0.0)),
    )


class MarginPoller:
    """DATA-13: polls POST /accounts/get-net-margin every margin_poll_interval_s
    and writes one margin_history row per in-scope market per cycle.

    Mirrors ELiqPoller pattern exactly: run_one_cycle / loop split, backoff on
    failure, degraded event after 5 consecutive failures.

    Parameters
    ----------
    config:
        Live BotConfig. Reads `data.margin_poll_interval_s`, `data.boros_account_id`,
        `markets`.
    conn:
        SQLite WAL connection (WAL mode, brain-owned).
    rest:
        Object with `async post_get_net_margin(account_id: int) -> dict`.
    run_id:
        Active run_id for traceability in margin_history rows.
    event_pub:
        Object with `async publish(topic: str, payload: dict)`.
        Used to emit `poller.margin.degraded` after 5 consecutive failures.
    """

    def __init__(
        self,
        config: Any,
        conn: sqlite3.Connection,
        rest: Any,
        run_id: str,
        event_pub: Any,
    ) -> None:
        self.interval: float = config.data.margin_poll_interval_s
        self.markets: list[str] = [m.market_id for m in config.markets]
        self.account_id: int = config.data.boros_account_id
        self.conn = conn
        self.rest = rest
        self.run_id = run_id
        self.event_pub = event_pub
        self._fail_count: int = 0

    async def run_one_cycle(self) -> None:
        """Run one polling cycle: fetch margin data, write one row per in-scope market.

        On fetch failure after all retries: log ERROR, publish degraded event when
        _fail_count >= 5, and return without writing rows. Does not raise.
        """
        try:
            margin_data = await self._get_with_backoff()
        except Exception as exc:
            log.error(
                "margin_poller.fetch_failed",
                error=str(exc),
                fail_count=self._fail_count,
            )
            if self._fail_count >= 5:
                await self.event_pub.publish(
                    "poller.margin.degraded",
                    {"fail_count": self._fail_count},
                )
            return

        self._fail_count = 0
        chain_ts = await get_chain_time_cached()

        # POST /accounts/get-net-margin returns per-account aggregate (not per-market).
        # Fan out one row per market for MarginTrajectoryBreaker query convenience.
        net_margin, maintenance_margin, available_collateral = _parse_margin_response(margin_data)

        for market_id in self.markets:
            insert_margin_snapshot(
                self.conn,
                chain_ts=chain_ts,
                market_id=market_id,
                net_margin_usd=net_margin,
                maintenance_margin_usd=maintenance_margin,
                available_collateral_usd=available_collateral,
                run_id=self.run_id,
            )
            log.info(
                "margin_poller.row_written",
                market_id=market_id,
                net_margin_usd=net_margin,
                chain_ts=chain_ts,
            )
        self.conn.commit()

    async def _get_with_backoff(self) -> dict[str, Any]:
        """Fetch margin with exponential backoff on failure.

        Delays: [0.5, 1, 2, 4, 8] seconds (5 retries). Each failed attempt
        increments `self._fail_count` so that the degraded-event threshold
        (>= 5) fires after one exhausted-retry cycle when all 5 attempts fail.
        Raises the last exception if all retries fail.
        """
        last_exc: BaseException | None = None
        for delay in _BACKOFF_DELAYS:
            try:
                result: dict[str, Any] = await self.rest.post_get_net_margin(self.account_id)
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


async def run_margin_poller_loop(
    config: Any,
    run_id: str,
    conn: sqlite3.Connection,
    rest: Any,
    event_pub: Any,
) -> None:
    """Thin wrapper for spawning MarginPoller in main.py's asyncio spawn block.

    Mirrors e_liq_poller.run_eliq_poller_loop pattern.
    """
    poller = MarginPoller(config, conn, rest, run_id, event_pub)
    await poller.loop()
