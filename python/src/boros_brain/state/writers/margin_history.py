"""Single writer for the `margin_history` table (brain-owned). Plan 04-02.

PROTO-02 single-writer discipline. MarginPoller.run_one_cycle is the only
caller of insert_margin_snapshot. Any `INSERT INTO margin_history` outside
this module triggers scripts/sqlite_writer_lint.py.

Margin data is per-account aggregate from POST /accounts/get-net-margin
(SAFE-01 data source). The poller fans out one row per market_id in the
active market list for query convenience.

[[boros-rest-api-margin-endpoint]]: endpoint contract + assumed field shape
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

__all__ = ["insert_margin_snapshot", "read_margin_history"]


def insert_margin_snapshot(
    conn: sqlite3.Connection,
    *,
    chain_ts: int,
    market_id: str,
    net_margin_usd: float,
    maintenance_margin_usd: float,
    available_collateral_usd: float,
    run_id: str,
) -> None:
    """Insert one margin_history row.

    Caller owns transaction lifecycle — NO conn.commit() here (db.py contract).
    PROTO-02: only MarginPoller.run_one_cycle should call this function.
    """
    conn.execute(
        "INSERT INTO margin_history "
        "(chain_ts, market_id, net_margin_usd, maintenance_margin_usd, "
        " available_collateral_usd, run_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            chain_ts,
            market_id,
            net_margin_usd,
            maintenance_margin_usd,
            available_collateral_usd,
            run_id,
        ),
    )


def read_margin_history(
    sqlite_path: Path,
    *,
    market_id: str | None = None,
    since_ts: int | None = None,
) -> list[dict[str, Any]]:
    """Return margin_history rows as a list of dicts.

    Self-managing connection (opens + closes within this call). Used by
    MarginTrajectoryBreaker.check() and test fixtures.

    Parameters
    ----------
    sqlite_path:
        Path to the SQLite WAL state DB.
    market_id:
        If given, filter to this market only.
    since_ts:
        If given, return only rows with chain_ts >= since_ts.

    Returns
    -------
    list[dict]
        Ordered by chain_ts ASC. Each dict has keys:
        chain_ts, market_id, net_margin_usd, maintenance_margin_usd,
        available_collateral_usd, run_id.
    """
    from boros_brain.state.db import open_connection

    sql = (
        "SELECT chain_ts, market_id, net_margin_usd, maintenance_margin_usd, "
        "available_collateral_usd, run_id FROM margin_history WHERE 1=1"
    )
    params: list[object] = []
    if market_id is not None:
        sql += " AND market_id = ?"
        params.append(market_id)
    if since_ts is not None:
        sql += " AND chain_ts >= ?"
        params.append(since_ts)
    sql += " ORDER BY chain_ts ASC"

    with open_connection(sqlite_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "chain_ts": r[0],
            "market_id": r[1],
            "net_margin_usd": r[2],
            "maintenance_margin_usd": r[3],
            "available_collateral_usd": r[4],
            "run_id": r[5],
        }
        for r in rows
    ]
