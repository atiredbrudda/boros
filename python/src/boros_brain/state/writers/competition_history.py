"""Single writer for the `competition_history` table (brain-owned). Plan 03-02.

PROTO-02 single-writer discipline. CompetitionTracker.run_one_cycle is the only
caller of insert_competition_row. Any `INSERT INTO competition_history` outside
this module triggers scripts/sqlite_writer_lint.py.

data_source enum:
  'live'                  — REST + parquet both healthy
  'fallback_parquet_only' — REST degraded after N consecutive failures
                            (RewardShareModelConfig.fallback_to_parquet_after_rest_fails_n)

[[competition-tracker-data-sources-v05]] for Σ_others composition + AMM exclusion.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

DataSource = Literal["live", "fallback_parquet_only"]
_ALLOWED: frozenset[str] = frozenset({"live", "fallback_parquet_only"})

__all__ = ["insert_competition_row", "get_latest_competition"]


def insert_competition_row(
    conn: sqlite3.Connection,
    *,
    polled_at_utc: str,
    chain_ts: int | None,
    market_id: str,
    q_me_pendle: float,
    sigma_others_pendle: float,
    run_id: str,
    data_source: DataSource = "live",
) -> None:
    """Insert one competition_history row.

    Raises ValueError if data_source is not in {'live','fallback_parquet_only'}.
    The SQL CHECK constraint would also reject it, but surfacing a Python error
    before SQL gives a clean stack trace.

    Caller owns transaction lifecycle — NO conn.commit() here (db.py contract).
    """
    if data_source not in _ALLOWED:
        raise ValueError(
            f"data_source={data_source!r} not in {sorted(_ALLOWED)}"
        )
    conn.execute(
        "INSERT INTO competition_history "
        "(polled_at_utc, chain_ts, market_id, q_me_pendle, sigma_others_pendle, "
        " data_source, run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            polled_at_utc,
            chain_ts,
            market_id,
            q_me_pendle,
            sigma_others_pendle,
            data_source,
            run_id,
        ),
    )


def get_latest_competition(sqlite_path: Path, market_id: str):
    """Return most-recent competition_history row for market_id as a dict, or None."""
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            "SELECT polled_at_utc, chain_ts, market_id, q_me_pendle, "
            "sigma_others_pendle, data_source, run_id "
            "FROM competition_history WHERE market_id = ? "
            "ORDER BY polled_at_utc DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "polled_at_utc": row[0],
        "chain_ts": row[1],
        "market_id": row[2],
        "q_me_pendle": row[3],
        "sigma_others_pendle": row[4],
        "data_source": row[5],
        "run_id": row[6],
    }
