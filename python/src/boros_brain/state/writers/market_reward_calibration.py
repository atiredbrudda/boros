"""Single writer for the `market_reward_calibration` table. LOCKED D-01 (Plan 03-02).

Operator-manual per-market reward-budget calibration. Refreshed at daily re-screen
via `python -m boros_brain.reward_model calibrate ...`. data_source is ALWAYS
'operator' (enforced by SQL CHECK + hardcoded Python literal — NOT a caller-kwarg).

Supersedes the Phase 1 ELiqPoller carried concern. See
[[e-liq-per-epoch-source-decision]] for the full evidence log.

PROTO-02 single-writer discipline: any INSERT INTO market_reward_calibration
outside this module triggers scripts/sqlite_writer_lint.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import structlog

Source = Literal["dapp_ui", "team_statement", "pendle_docs"]
_ALLOWED_SOURCES: frozenset[str] = frozenset({"dapp_ui", "team_statement", "pendle_docs"})

__all__ = [
    "insert_market_reward_calibration",
    "get_latest_market_reward_calibration",
    "read_market_reward_calibration_history",
]


def _looks_like_iso8601(s: str) -> bool:
    """Minimal ISO8601 sanity check — must start with YYYY-MM-DDT."""
    import re

    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T", s))


def insert_market_reward_calibration(
    sqlite_path: Path,
    *,
    market_id: str,
    e_liq_per_epoch_pendle: float,
    long_side_split: float,
    short_side_split: float,
    calibrated_at_utc: str,
    effective_at_utc: str,
    next_refresh_at_utc: str,
    source: Source = "dapp_ui",
    run_id: str,
) -> None:
    """Self-contained single-writer — opens its own connection.

    Raises ValueError BEFORE SQL round-trip if:
      - source not in allowed enum, OR
      - splits don't sum to 1.0 (P3-4 guard), OR
      - e_liq_per_epoch_pendle < 0.0, OR
      - effective_at_utc / next_refresh_at_utc not ISO8601-shaped.

    SQL CHECK constraints (data_source = 'operator', source enum, splits range,
    e_liq nonneg) are belt-and-braces.

    data_source is hardcoded to 'operator' inside the SQL — NOT a caller kwarg.

    W2a (Phase 05.2): effective_at_utc and next_refresh_at_utc are now required
    kwargs. They are persisted to the columns added by Alembic migration 0008.
    """
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"source={source!r} not in {sorted(_ALLOWED_SOURCES)}")
    if abs(long_side_split + short_side_split - 1.0) > 1e-9:
        raise ValueError(
            f"long_side_split + short_side_split must == 1.0 "
            f"(got {long_side_split} + {short_side_split} "
            f"= {long_side_split + short_side_split}). P3-4 guard."
        )
    if e_liq_per_epoch_pendle < 0.0:
        raise ValueError(f"e_liq_per_epoch_pendle must be >= 0.0, got {e_liq_per_epoch_pendle}")
    if not _looks_like_iso8601(effective_at_utc):
        raise ValueError(
            f"effective_at_utc must be ISO8601-shaped (YYYY-MM-DDT...), got {effective_at_utc!r}"
        )
    if not _looks_like_iso8601(next_refresh_at_utc):
        raise ValueError(
            f"next_refresh_at_utc must be ISO8601-shaped (YYYY-MM-DDT...), got {next_refresh_at_utc!r}"
        )

    from boros_brain.state.db import open_connection

    log = structlog.get_logger(__name__)

    with open_connection(sqlite_path) as conn:
        conn.execute(
            "INSERT INTO market_reward_calibration "
            "(market_id, e_liq_per_epoch_pendle, long_side_split, short_side_split, "
            " calibrated_at_utc, effective_at_utc, next_refresh_at_utc, "
            " data_source, source, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'operator', ?, ?)",
            (
                market_id,
                e_liq_per_epoch_pendle,
                long_side_split,
                short_side_split,
                calibrated_at_utc,
                effective_at_utc,
                next_refresh_at_utc,
                source,
                run_id,
            ),
        )
    log.info(
        "reward_model.calibration_persisted",
        market_id=market_id,
        e_liq_per_epoch_pendle=e_liq_per_epoch_pendle,
        long_side_split=long_side_split,
        short_side_split=short_side_split,
        effective_at_utc=effective_at_utc,
        next_refresh_at_utc=next_refresh_at_utc,
        source=source,
        run_id=run_id,
    )


def get_latest_market_reward_calibration(sqlite_path: Path, market_id: str) -> dict[str, Any] | None:
    """Return most-recent calibration row for market_id as a dict, or None.

    W2a: Returns effective_at_utc and next_refresh_at_utc in the dict.
    Order-by stays calibrated_at_utc DESC for backwards compat; a future plan
    can switch to effective_at_utc DESC if epoch-keyed reads are required.
    """
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            "SELECT market_id, e_liq_per_epoch_pendle, long_side_split, "
            "short_side_split, calibrated_at_utc, effective_at_utc, "
            "next_refresh_at_utc, data_source, source, run_id "
            "FROM market_reward_calibration WHERE market_id = ? "
            "ORDER BY calibrated_at_utc DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "market_id": row[0],
        "e_liq_per_epoch_pendle": row[1],
        "long_side_split": row[2],
        "short_side_split": row[3],
        "calibrated_at_utc": row[4],
        "effective_at_utc": row[5],
        "next_refresh_at_utc": row[6],
        "data_source": row[7],
        "source": row[8],
        "run_id": row[9],
    }


def read_market_reward_calibration_history(sqlite_path: Path, market_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return up to `limit` calibration rows for market_id ordered DESC by calibrated_at_utc.

    rows[0] is the latest calibration; rows[-1] is the oldest within the window.
    Used by SideBudgetBreaker (SAFE-08) to compare the latest split vs the
    epoch-lag split.

    Read-only — not subject to PROTO-02 single-writer lint.
    """
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        rows = conn.execute(
            "SELECT market_id, e_liq_per_epoch_pendle, long_side_split, short_side_split, "
            "calibrated_at_utc, source FROM market_reward_calibration WHERE market_id = ? "
            "ORDER BY calibrated_at_utc DESC LIMIT ?",
            (market_id, limit),
        ).fetchall()
    return [
        dict(
            zip(
                [
                    "market_id",
                    "e_liq_per_epoch_pendle",
                    "long_side_split",
                    "short_side_split",
                    "calibrated_at_utc",
                    "source",
                ],
                r,
                strict=False,
            )
        )
        for r in rows
    ]
