#!/usr/bin/env python3
"""Phase 05.4-01 Bug A: insert prior+current operator calibration rows for BINANCE-ETHUSDT-25SEP2026.

Idempotent: writer's pre-flight raises ValueError on duplicate (market_id, effective_at_utc).
We catch ValueError matching the duplicate signature and treat as success (no-op).

[[phase-05-4-bug-a-calibration-migration]]

Why these values (from 05.4-CONTEXT.md lines 95-97 + dapp UI calibration):
  - e_liq_per_epoch_pendle=309.96: operator-calibrated value from dapp UI snapshot
  - prior long_side_split=0.327: dapp UI snapshot before the 2026-04-23 epoch shift
  - current long_side_split=0.760: dapp UI snapshot at/after 2026-04-23 (W0 evidence E3)
  - effective_at_utc=2026-03-15 for prior: conservative anchor <= replay window start
  - effective_at_utc=2026-04-23 for current: W0 evidence E3 epoch-boundary inference

Bug A context: Alembic migration 0008 was authored (adds effective_at_utc +
next_refresh_at_utc columns) but never applied to state/state.sqlite. Without the
columns, _load_operator_calibration_history raises OperationalError and the engine
falls through to default fallback values (e_liq=100, side_split=0.5), producing
~4.5M no_operator_calibration warnings and a reward leg ~3-5x off.

Run AFTER applying the migration:
  uv run --directory python python ../scripts/apply_alembic_migration.py \\
      sqlite:///$(pwd)/state/state.sqlite
"""
from __future__ import annotations

import sys
from pathlib import Path

import sqlite3 as _sqlite3

from boros_brain.state.writers.market_reward_calibration import (
    insert_market_reward_calibration,
)

MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"

PRIOR_ROW = dict(
    market_id=MARKET_ID,
    e_liq_per_epoch_pendle=309.96,
    long_side_split=0.327,
    short_side_split=0.673,
    calibrated_at_utc="2026-04-30T08:30:26+00:00",
    effective_at_utc="2026-03-15T00:00:00+00:00",
    next_refresh_at_utc="2026-04-23T00:00:00+00:00",
    source="dapp_ui",
    run_id="phase054-bug-a-prior",
)
CURRENT_ROW = dict(
    market_id=MARKET_ID,
    e_liq_per_epoch_pendle=309.96,
    long_side_split=0.760,
    short_side_split=0.240,
    calibrated_at_utc="2026-04-30T08:30:30+00:00",
    effective_at_utc="2026-04-23T00:00:00+00:00",
    next_refresh_at_utc="2026-05-02T00:00:00+00:00",
    source="dapp_ui",
    run_id="phase054-bug-a-current",
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <absolute-path-to-state.sqlite>", file=sys.stderr)
        return 2
    sqlite_path = Path(argv[1]).resolve()
    if not sqlite_path.exists():
        print(
            f"error: {sqlite_path} does not exist (run apply_alembic_migration.py first)",
            file=sys.stderr,
        )
        return 2

    inserted = 0
    skipped = 0
    # Note: market_reward_calibration has no UNIQUE(market_id, effective_at_utc)
    # constraint, so we must pre-check via SELECT to achieve idempotency.
    conn = _sqlite3.connect(str(sqlite_path))
    try:
        existing_effective_ats = {
            row[0]
            for row in conn.execute(
                "SELECT effective_at_utc FROM market_reward_calibration "
                "WHERE data_source='operator' AND market_id=? AND run_id IN (?, ?)",
                (MARKET_ID, PRIOR_ROW["run_id"], CURRENT_ROW["run_id"]),
            ).fetchall()
        }
    finally:
        conn.close()

    for label, row in (("prior", PRIOR_ROW), ("current", CURRENT_ROW)):
        if row["effective_at_utc"] in existing_effective_ats:
            skipped += 1
            print(f"skipped {label}-epoch row (already present): effective_at_utc={row['effective_at_utc']}")
        else:
            insert_market_reward_calibration(sqlite_path, **row)
            inserted += 1
            print(f"inserted {label}-epoch row (effective_at_utc={row['effective_at_utc']})")
    print(f"done: inserted={inserted}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
