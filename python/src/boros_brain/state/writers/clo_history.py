"""Single writer for the `clo_history` table (brain-owned).

PROTO-02 single-writer discipline. Only markets_poller imports this module;
other readers go through DuckDB.

Two public functions:
  - insert_clo_snapshot(conn, ...) — low-level; caller owns the connection
    (used by tests and any code that manages its own transaction lifecycle).
  - insert_clo_history(sqlite_path, ...) — self-contained; opens + commits
    its own connection via open_connection() contextmanager (used by
    MarketsPoller so the poller doesn't need to manage connection lifecycle).

Column names match the Wave-0 canonical schema (01-02 0001_initial_8_tables):
  snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw
NOT camelCase API wire names.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

from boros_brain.state.db import open_connection

log = structlog.get_logger(__name__)


def insert_clo_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_ts: int,
    market_id: str,
    clo_lower_thresh: float,
    clo_upper_thresh: float,
    f_index_raw: int | None = None,
) -> None:
    """Insert one CLO + fIndex snapshot (low-level — caller owns the connection).

    `f_index_raw` is nullable for historical backfills that predate fIndex
    decoding. The 01-09 live poller populates it on every call.
    """
    conn.execute(
        "INSERT INTO clo_history "
        "(snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw) "
        "VALUES (?, ?, ?, ?, ?)",
        (snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw),
    )


def insert_clo_history(
    sqlite_path: Path | str,
    *,
    market_id: str,
    snapshot_ts: int,
    clo_lower_thresh: float,
    clo_upper_thresh: float,
    f_index_raw: int | None,
) -> None:
    """Append one row to clo_history. Self-contained — manages its own connection.

    Called by MarketsPoller.tick() after determining a change has occurred
    relative to the last observed (clo_lower, clo_upper, f_index_raw) tuple.

    f_index_raw is nullable (pass None when fIndex decode fails for a market).

    Args:
        sqlite_path: Path to the SQLite DB (from config.infra.sqlite_path).
        market_id: String market identifier (imData.symbol, e.g. "BINANCE-ETHUSDT-29MAY2026").
        snapshot_ts: Chain-time unix timestamp at poll time (from chain_time.now_cached()).
        clo_lower_thresh: CLO lower threshold (float; API int coerced).
        clo_upper_thresh: CLO upper threshold (float; API int coerced).
        f_index_raw: Decoded floatingIndex_raw from fIndexOracle bytes26 payload.
            None if the decode failed (T-01-09-02: non-fatal; poller logs WARN).
    """
    with open_connection(sqlite_path) as conn:
        conn.execute(
            "INSERT INTO clo_history "
            "(snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw) "
            "VALUES (?, ?, ?, ?, ?)",
            (snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw),
        )
    log.info(
        "clo_history.appended",
        market_id=market_id,
        snapshot_ts=snapshot_ts,
        clo_lower_thresh=clo_lower_thresh,
        clo_upper_thresh=clo_upper_thresh,
        f_index_raw=f_index_raw,
    )
