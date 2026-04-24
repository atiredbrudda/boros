"""REWARD-02: CompetitionTracker — 5s REST poll + parquet read.

Composes two sources to compute Σ_others for the reward-share formula:
  - Q_me  via POST /open-api/v2/accounts/all-limit-orders (operator's own orders)
  - Total book via DuckDB aggregation over parquet.order_book_raw within the
    [clo_lower, clo_upper] CLO range.

Σ_others = total_raw_book_in_range - Q_me. AMM share is EXCLUDED by reading
parquet.order_book_raw (NOT order_book_combined) — T-03-06 mitigation; AMMs
do not compete for LO Liquidity Rewards.

Degraded-mode per RESEARCH §REWARD-02:
  - N=5 consecutive REST failures → data_source='fallback_parquet_only',
    Q_me estimated from SQLite open_orders (Phase-1 writer),
    `competition_tracker.rest_degraded` event emitted on the 5th failure.

[[competition-tracker-data-sources-v05]]
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ..config.schema import BotConfig
from ..data.chain_time import now_cached as get_chain_time_cached
from ..state.writers.competition_history import insert_competition_row

log = structlog.get_logger(__name__)

# Backoff delays in seconds: [0.5, 1, 2, 4, 8] — five retry windows.
_BACKOFF_DELAYS = [0.5, 1.0, 2.0, 4.0, 8.0]

__all__ = ["CompetitionTracker", "run_competition_tracker_loop"]


class CompetitionTracker:
    """Polls /open-api/v2/accounts/all-limit-orders + reads parquet.order_book_raw.

    Parameters
    ----------
    config:
        Live BotConfig. Reads `reward_share_model.competition_poll_interval_s`
        and `reward_share_model.fallback_to_parquet_after_rest_fails_n`.
    conn:
        SQLite WAL connection (brain-owned, single-writer).
    rest:
        Object with `async post_all_limit_orders(user_address, account_id)`.
        Returns list[dict] of orders with at least {marketId, sz}.
    run_id:
        Active run_id for traceability in competition_history rows.
    event_pub:
        Object with `async publish(topic, payload)` for ZMQ events.
    sqlite_path:
        Filesystem path used by the analytical DuckDB connection (read-only attach).
    """

    def __init__(
        self,
        config: BotConfig,
        conn: sqlite3.Connection,
        rest: Any,
        run_id: str,
        event_pub: Any,
        sqlite_path: Path,
    ) -> None:
        self.config = config
        self.conn = conn
        self.rest = rest
        self.run_id = run_id
        self.event_pub = event_pub
        self.sqlite_path = sqlite_path
        self.interval = config.reward_share_model.competition_poll_interval_s
        self.fail_threshold = (
            config.reward_share_model.fallback_to_parquet_after_rest_fails_n
        )
        self.markets = [m.market_id for m in config.markets]
        self._fail_count: int = 0
        self._degraded_emitted: bool = False

    async def run_one_cycle(self) -> None:
        """One (REST + parquet) pass; writes one competition_history row per market."""
        chain_ts = int(await get_chain_time_cached())
        polled_at = datetime.now(UTC).isoformat()

        for market_id in self.markets:
            try:
                q_me = await self._get_q_me_with_backoff(market_id)
                data_source = "live"
                self._fail_count = 0
                self._degraded_emitted = False
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "competition_tracker.rest_fetch_failed",
                    error=str(exc),
                    fail_count=self._fail_count,
                    market_id=market_id,
                )
                if (
                    self._fail_count >= self.fail_threshold
                    and not self._degraded_emitted
                ):
                    await self.event_pub.publish(
                        "competition_tracker.rest_degraded",
                        {"fail_count": self._fail_count, "market_id": market_id},
                    )
                    self._degraded_emitted = True
                # Fallback: estimate Q_me from SQLite open_orders.
                q_me = self._estimate_q_me_from_open_orders(market_id)
                data_source = "fallback_parquet_only"

            # Read Σ_others from parquet.order_book_raw (AMM share excluded).
            sigma_others = self._read_sigma_others_from_parquet(
                market_id, chain_ts, q_me
            )

            insert_competition_row(
                self.conn,
                polled_at_utc=polled_at,
                chain_ts=chain_ts,
                market_id=market_id,
                q_me_pendle=q_me,
                sigma_others_pendle=sigma_others,
                run_id=self.run_id,
                data_source=data_source,
            )
            self.conn.commit()  # tracker owns its transaction lifecycle

    async def _get_q_me_with_backoff(self, market_id: str) -> float:
        """POST /open-api/v2/accounts/all-limit-orders — retry with backoff.

        Returns Q_me in PENDLE-units (v0.5 placeholder: REST-returned size used
        directly; Plan 03-03 Sizer wires the proper YU↔PENDLE conversion via
        notional_per_yu_usd / pendle_price_usd).
        """
        last_exc: BaseException | None = None
        for delay in _BACKOFF_DELAYS:
            try:
                results = await self.rest.post_all_limit_orders(
                    user_address=self.config.root_wallet_address,
                    account_id=0,
                )
                return self._sum_q_me(results, market_id)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self._fail_count += 1
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _sum_q_me(self, orders: list[dict], market_id: str) -> float:
        """Sum our own order sizes for the market in PENDLE-units (v0.5 proxy).

        v0.5: assumes REST returns sizes already in PENDLE-equivalent units via
        the wallet's accounting. If the field is in YU wei, caller converts via
        MarketCalibration.notional_per_yu_usd / pendle_price_usd.
        """
        total = 0.0
        for o in orders:
            if o.get("marketId") == market_id or o.get("symbol") == market_id:
                sz_raw = o.get("sz", 0)
                if isinstance(sz_raw, str):
                    # Wei-as-string per Phase-1 ingester convention.
                    try:
                        size_yu = float(sz_raw) / 1e18
                    except ValueError:
                        size_yu = 0.0
                else:
                    size_yu = float(sz_raw)
                total += size_yu
        return total

    def _read_sigma_others_from_parquet(
        self, market_id: str, chain_ts: int, q_me: float
    ) -> float:
        """DuckDB query: sum raw_book size in [clo_lower, clo_upper] - q_me.

        T-03-06 AMM exclusion: reads `parquet.order_book_raw` (NOT
        order_book_combined). raw_book contains only LO competitors —
        AMM share is the (combined - raw) delta.
        """
        from ..duckdb_layer.setup import open_analytical_conn

        # Resolve parquet root from infra config (Phase 1 convention).
        parquet_root = Path("data/parquet")

        try:
            conn = open_analytical_conn(
                str(self.sqlite_path), str(parquet_root)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "competition_tracker.duckdb_open_failed",
                market_id=market_id,
                error=str(exc),
            )
            return 0.0

        try:
            # Get latest CLO bounds from clo_history (DATA-06 writer).
            clo_row = conn.execute(
                "SELECT clo_lower_thresh, clo_upper_thresh FROM clo_history "
                "WHERE market_id = ? ORDER BY snapshot_ts DESC LIMIT 1",
                [market_id],
            ).fetchone()
            if clo_row is None:
                log.warning(
                    "competition_tracker.no_clo_history",
                    market_id=market_id,
                )
                return 0.0
            clo_lower, clo_upper = clo_row

            # Sum raw-book sizes within the CLO range at the latest snapshot
            # <= chain_ts. AMM share is excluded by reading order_book_raw,
            # NOT order_book_combined (T-03-06).
            sigma_row = conn.execute(
                """
                WITH latest AS (
                    SELECT MAX(snapshot_ts) AS ts
                    FROM order_book_raw
                    WHERE market_id = ? AND snapshot_ts <= ?
                )
                SELECT COALESCE(SUM(sz_float), 0.0) AS sum_sz
                FROM order_book_raw, latest
                WHERE order_book_raw.market_id = ?
                  AND order_book_raw.snapshot_ts = latest.ts
                  AND order_book_raw.tick BETWEEN ? AND ?
                """,
                [market_id, chain_ts, market_id, clo_lower, clo_upper],
            ).fetchone()
            total_raw = float(sigma_row[0]) if sigma_row else 0.0
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "competition_tracker.parquet_query_failed",
                market_id=market_id,
                error=str(exc),
            )
            return 0.0
        finally:
            conn.close()

        sigma_others = max(0.0, total_raw - q_me)
        return sigma_others

    def _estimate_q_me_from_open_orders(self, market_id: str) -> float:
        """Fallback when REST is degraded: sum sizes from SQLite state.open_orders.

        size_wei is stored as TEXT in open_orders (256-bit safe); we cast to
        float on the SQL side with COALESCE on the empty-rows case.
        """
        # SQLite's CAST handles the wei-text path; treat 1e18 as the YU-wei
        # divisor (placeholder mirroring _sum_q_me v0.5 semantics).
        cursor = self.conn.execute(
            "SELECT COALESCE(SUM(CAST(size_wei AS REAL)), 0.0) "
            "FROM open_orders WHERE market_id = ? AND status = 'filling'",
            (market_id,),
        )
        row = cursor.fetchone()
        size_total_wei = float(row[0]) if row else 0.0
        return size_total_wei / 1e18 if size_total_wei else 0.0


async def run_competition_tracker_loop(
    config: BotConfig,
    run_id: str,
    *,
    conn: sqlite3.Connection,
    rest: Any,
    event_pub: Any,
) -> None:
    """Spawned from brain.main via asyncio.create_task. Plan 03-04 wires this."""
    sqlite_path = Path(config.infra.sqlite_path)
    tracker = CompetitionTracker(
        config, conn, rest, run_id, event_pub, sqlite_path
    )
    log.info(
        "competition_tracker.loop_started",
        run_id=run_id,
        interval_s=tracker.interval,
    )
    while True:
        try:
            await tracker.run_one_cycle()
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "competition_tracker.cycle_failed",
                run_id=run_id,
                err=str(exc),
            )
        await asyncio.sleep(tracker.interval)
