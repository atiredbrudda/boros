"""Single writer for the `reward_budget_history` table (brain-owned).

PROTO-02 single-writer discipline. DATA-11 polled E_liq writes here only.

**B6 pitfall guard:** `data_source` must be 'polled' (forward-only live poll)
or 'synthetic_current' (historical backfill reconstructed from current budget).
The DB CHECK constraint enforces this at the SQL layer; this writer also rejects
invalid values at the Python layer so callers get a clean error before the SQL
round-trip. Phase-5 backtest filters rows by `data_source='polled'` to avoid
current-budget-synthetic leakage into historical P&L.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

DataSource = Literal["polled", "synthetic_current"]
_ALLOWED: frozenset[str] = frozenset({"polled", "synthetic_current"})


def insert_reward_budget(
    conn: sqlite3.Connection,
    *,
    snapshot_ts: int,
    market_id: str,
    e_liq_per_epoch: float,
    long_budget: float,
    short_budget: float,
    data_source: DataSource,
) -> None:
    """Insert one reward-budget snapshot.

    Raises `ValueError` if `data_source` is not in {'polled', 'synthetic_current'}
    — the SQL CHECK constraint would also reject it, but surfacing a ValueError
    before the DB round-trip gives the caller a clearer stack trace (B6 guard).
    """
    if data_source not in _ALLOWED:
        raise ValueError(f"data_source={data_source!r} not in {sorted(_ALLOWED)} (B6 pitfall guard)")
    conn.execute(
        "INSERT INTO reward_budget_history "
        "(snapshot_ts, market_id, e_liq_per_epoch, long_budget, short_budget, data_source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            snapshot_ts,
            market_id,
            e_liq_per_epoch,
            long_budget,
            short_budget,
            data_source,
        ),
    )
