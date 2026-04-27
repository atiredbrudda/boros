#!/usr/bin/env python3
"""Backfill `reward_budget_history` with synthetic_current rows for Wave-1 backtest unblock.

Why this exists
---------------
Per LOCKED D-01 ([[e-liq-per-epoch-source-decision]]) the live `ELiqPoller` cannot work
because GET /markets does NOT carry `liquidityRewardPerEpoch / longBudget / shortBudget`.
Operator-manual calibration via `python -m boros_brain.reward_model calibrate` is the v0.5
answer for `market_reward_calibration`, but the screener (`brain.screener.filter`) still
reads `reward_budget_history` for its `r_apr_potential` ranking. With Wave-1 ingest only
populating parquet (market_trades, order_book, etc.) and never the SQLite spine, the table
is empty — every market gets `r_apr_potential=None`, no market can be ranked, and the
economics gate has no input.

This script writes one `data_source='synthetic_current'` row per market to
`reward_budget_history` using the operator-supplied anchor values. It uses the existing
single-writer `insert_reward_budget_row` (PROTO-02 single-writer discipline preserved).

The `synthetic_current` lineage marker is exactly what the schema CHECK constraint
reserves for "historical backfill reconstructed from current budget" (PITFALLS §B6).
The backtest replay engine (`brain.backtest.replay`) explicitly filters these rows out
of P&L computation but the screener does NOT — its query is just `ORDER BY chain_ts DESC
LIMIT 1` regardless of lineage. That asymmetry is intentional: the screener needs ANY
budget signal to rank markets; the backtest needs operator-attested rows only.

Usage
-----
    # Backfill from parquet markets (Wave-1 default — discovers markets in
    # data/parquet/market_trades/) using the documented anchor values
    python scripts/backfill_reward_budget_history.py

    # Override anchor values + sqlite location
    python scripts/backfill_reward_budget_history.py \\
        --sqlite-path python/state/state.sqlite \\
        --e-liq-pendle 273.0 \\
        --long-share 0.14 \\
        --short-share 0.86

    # Restrict to a specific market list (canonical IDs)
    python scripts/backfill_reward_budget_history.py \\
        --markets BINANCE-ETHUSDT-29MAY2026 HYPERLIQUID-BTC-29MAY2026

    # Dry run — print what would be written, don't touch SQLite
    python scripts/backfill_reward_budget_history.py --dry-run

Verification
------------
    sqlite3 python/state/state.sqlite \\
        "SELECT market_id, e_liq_per_epoch, data_source FROM reward_budget_history;"

    cd python && uv run python -m boros_brain.screener --run \\
        --config ../strategy/v0.5-default.yaml
    # Expect var/reports/screener_metrics.json to contain at least one market with
    # non-null r_apr_potential.

Defaults
--------
    e_liq_per_epoch_pendle = 273.0   (ETHUSDT-29MAY2026 anchor — see sizer/cli.py:82-83)
    long_share             = 0.14    (per [[market-reward-calibration-operator-workflow]])
    short_share            = 0.86    (long+short MUST sum to 1.0 ± 1e-9)

These anchors apply uniformly across all markets in v0.5 backtest. v1.0 per-market
operator calibration via `python -m boros_brain.reward_model calibrate` supersedes.

[[e-liq-per-epoch-source-decision]]
[[market-reward-calibration-operator-workflow]]
[[live-e-liq-polling-data-11]]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical anchor values per [[market-reward-calibration-operator-workflow]].
# Identical to the sizer CLI defaults (python/src/boros_brain/sizer/cli.py:82-83).
DEFAULT_E_LIQ_PER_EPOCH_PENDLE = 273.0
DEFAULT_LONG_SHARE = 0.14
DEFAULT_SHORT_SHARE = 0.86


def discover_markets_from_parquet(parquet_root: Path) -> list[str]:
    """Discover canonical market IDs from `data/parquet/market_trades/` partitions.

    Strips the `market_id=` prefix and the leading numeric archive prefix
    (`^\\d+-`) so the returned IDs match what the screener queries SQLite with.

    Returns sorted list (stable order — important for deterministic backfill output).
    """
    import re

    archive_prefix_re = re.compile(r"^\d+-")
    market_trades_dir = parquet_root / "market_trades"
    if not market_trades_dir.exists():
        return []
    canonical: set[str] = set()
    for entry in market_trades_dir.iterdir():
        if not entry.is_dir() or not entry.name.startswith("market_id="):
            continue
        prefixed = entry.name[len("market_id=") :]
        # Strip the leading numeric prefix to get the canonical SQLite-keyed ID.
        canonical_id = archive_prefix_re.sub("", prefixed, count=1)
        canonical.add(canonical_id)
    return sorted(canonical)


def backfill_one_market(
    conn: sqlite3.Connection,
    *,
    market_id: str,
    e_liq_per_epoch: float,
    long_share: float,
    short_share: float,
    chain_ts: int,
    run_id: str,
    dry_run: bool,
) -> bool:
    """Insert one `synthetic_current` row. Returns True iff a row was written.

    Uses the existing single-writer `insert_reward_budget_row` to honour PROTO-02.
    Skips (returns False) if a `synthetic_current` row already exists for this
    market (idempotent re-run safety — the screener picks the most recent row by
    chain_ts so duplicates wouldn't break correctness, but they would mask schema
    drift in subsequent debug sessions).
    """
    existing = conn.execute(
        "SELECT COUNT(*) FROM reward_budget_history WHERE market_id = ? AND data_source = 'synthetic_current'",
        (market_id,),
    ).fetchone()[0]
    if existing > 0:
        return False

    if dry_run:
        return True

    # Lazy import — keeps the script's import cost down and avoids forcing
    # the boros_brain package to be installed for `--help` / `--dry-run`.
    sys.path.insert(0, str(REPO_ROOT / "python" / "src"))
    from boros_brain.state.writers.reward_budget_history import insert_reward_budget_row

    long_budget = e_liq_per_epoch * long_share
    short_budget = e_liq_per_epoch * short_share

    insert_reward_budget_row(
        conn,
        market_id=market_id,
        e_liq_per_epoch=e_liq_per_epoch,
        long_budget=long_budget,
        short_budget=short_budget,
        chain_ts=chain_ts,
        run_id=run_id,
        data_source="synthetic_current",
    )
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scripts/backfill_reward_budget_history.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--sqlite-path",
        default=str(REPO_ROOT / "python" / "state" / "state.sqlite"),
        help=(
            "Path to the SQLite spine to backfill. Default: python/state/state.sqlite "
            "(the alembic-current DB). For the legacy state/state.sqlite (alembic 0002), "
            "you must first upgrade it past 0007 separately."
        ),
    )
    p.add_argument(
        "--parquet-root",
        default=str(REPO_ROOT / "data" / "parquet"),
        help="Parquet root for market discovery (default: data/parquet)",
    )
    p.add_argument(
        "--markets",
        nargs="+",
        default=None,
        help=(
            "Explicit canonical market IDs to backfill (overrides --parquet-root "
            "discovery). Use the un-prefixed form, e.g. BINANCE-ETHUSDT-29MAY2026."
        ),
    )
    p.add_argument(
        "--e-liq-pendle",
        type=float,
        default=DEFAULT_E_LIQ_PER_EPOCH_PENDLE,
        help=f"E_liq_per_epoch_pendle anchor (default {DEFAULT_E_LIQ_PER_EPOCH_PENDLE})",
    )
    p.add_argument(
        "--long-share",
        type=float,
        default=DEFAULT_LONG_SHARE,
        help=f"Long-side share (default {DEFAULT_LONG_SHARE})",
    )
    p.add_argument(
        "--short-share",
        type=float,
        default=DEFAULT_SHORT_SHARE,
        help=f"Short-side share (default {DEFAULT_SHORT_SHARE})",
    )
    p.add_argument(
        "--chain-ts",
        type=int,
        default=None,
        help=(
            "Chain timestamp to stamp on the row (unix seconds). "
            "Default: current wall-clock UTC. Screener picks MAX(chain_ts) so "
            "any value works for unblocking — set explicitly only for "
            "deterministic test reproduction."
        ),
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="run_id for traceability (default: synthesized 'backfill-{epoch}')",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written; do not touch SQLite.",
    )
    args = p.parse_args(argv)

    # Validate split sum (mirrors the writer-layer P3-4 guard for clearer errors).
    if abs(args.long_share + args.short_share - 1.0) > 1e-9:
        print(
            f"ERROR: long_share ({args.long_share}) + short_share ({args.short_share}) "
            f"= {args.long_share + args.short_share}, must equal 1.0 ± 1e-9 (P3-4 guard).",
            file=sys.stderr,
        )
        return 2

    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.exists():
        print(f"ERROR: SQLite file not found: {sqlite_path}", file=sys.stderr)
        return 2

    # Discover markets.
    if args.markets:
        markets = list(args.markets)
        source = "explicit --markets"
    else:
        markets = discover_markets_from_parquet(Path(args.parquet_root))
        source = f"parquet ({args.parquet_root})"

    if not markets:
        print(
            "ERROR: No markets to backfill — pass --markets or ensure "
            "data/parquet/market_trades/ has market_id=... partitions.",
            file=sys.stderr,
        )
        return 2

    chain_ts = args.chain_ts if args.chain_ts is not None else int(time.time())
    run_id = args.run_id or f"backfill-{chain_ts}"

    print(f"# Backfill reward_budget_history (synthetic_current)")
    print(f"# sqlite_path : {sqlite_path}")
    print(f"# market source: {source}")
    print(f"# markets ({len(markets)}): {', '.join(markets[:3])}{'...' if len(markets) > 3 else ''}")
    print(f"# e_liq_per_epoch_pendle: {args.e_liq_pendle}")
    print(f"# long_share / short_share: {args.long_share} / {args.short_share}")
    print(f"# chain_ts : {chain_ts}")
    print(f"# run_id   : {run_id}")
    print(f"# dry_run  : {args.dry_run}")
    print()

    # Open connection. Single transaction for all inserts (caller-owned transaction
    # discipline per `state/db.py` contract — `insert_reward_budget_row` does NOT
    # commit internally).
    conn = sqlite3.connect(str(sqlite_path))
    try:
        # Force WAL since the live brain uses it; backfill respects existing journal mode.
        conn.execute("PRAGMA journal_mode=WAL;")

        written = 0
        skipped = 0
        for mid in markets:
            try:
                wrote = backfill_one_market(
                    conn,
                    market_id=mid,
                    e_liq_per_epoch=args.e_liq_pendle,
                    long_share=args.long_share,
                    short_share=args.short_share,
                    chain_ts=chain_ts,
                    run_id=run_id,
                    dry_run=args.dry_run,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  {mid}: {exc}", file=sys.stderr)
                conn.rollback()
                return 1
            if wrote:
                written += 1
                tag = "DRY " if args.dry_run else "WROTE"
                print(f"{tag} {mid}")
            else:
                skipped += 1
                print(f"SKIP  {mid} (synthetic_current row already exists)")

        if not args.dry_run:
            conn.commit()
        print()
        print(f"Done: {written} written, {skipped} skipped, {len(markets)} total.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
