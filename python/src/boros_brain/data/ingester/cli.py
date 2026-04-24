"""CLI: python -m boros_brain.data.ingester.cli --kind <k> --src <path> [options] --out <parquet_root>

Dispatch NDJSON → Hive-partitioned parquet for DATA-01..04.
Emits RUN_MANIFEST on every run (PROTO-01 / CLAUDE.md Engineering Protocol #3).

Usage:
    uv run --directory python python -m boros_brain.data.ingester.cli \\
        --kind market_trades \\
        --src data/ndjson/market-trades/ETH/2025-08.ndjson \\
        --market-id ETH \\
        --out data/parquet

1 GB/file guidance: the underlying polars sink_parquet uses streaming — each file
is processed without loading the full dataset into RAM. For files larger than 1 GB
consider splitting upstream before calling this CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

from boros_brain.config.loader import load_config
from boros_brain.logging.structlog_setup import configure_logging
from boros_brain.manifest.writer import build_run_manifest, write_manifest

from .market_trades import ingest_market_trades
from .order_book import ingest_order_book_combined, ingest_order_book_raw
from .settlement_md import ingest_settlement_md
from .underlying_apr import ingest_underlying_apr


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — dispatches to the appropriate ingester based on --kind."""
    p = argparse.ArgumentParser(
        description="Boros NDJSON ingester — DATA-01..04. 1 GB/file max recommended.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--kind",
        required=True,
        choices=["market_trades", "order_book_raw", "order_book_combined", "underlying_apr", "settlement_md"],
        help="Which NDJSON shape to ingest",
    )
    p.add_argument("--src", required=True, type=Path, help="Primary NDJSON source path")
    p.add_argument("--market-id", dest="market_id", help="Market identifier (e.g. ETH)")
    p.add_argument("--exchange", help="Exchange name for underlying_apr (e.g. binance)")
    p.add_argument("--tick-size", dest="tick_size", help="Tick size string for order_book_combined (e.g. 0.01)")
    p.add_argument(
        "--market-data-src",
        dest="market_data_src",
        type=Path,
        help="For settlement_md: path to market-data NDJSON (optional)",
    )
    p.add_argument("--out", required=True, type=Path, help="Parquet root directory")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("strategy/v0.5-default.yaml"),
        help="BotConfig YAML (default: strategy/v0.5-default.yaml)",
    )
    args = p.parse_args(argv)

    # ── RUN_MANIFEST — must be emitted before first log line (PROTO-01) ──────
    config = load_config(args.config)
    manifest = build_run_manifest(config)
    # Write sidecar + SQLite row; logs_dir defaults to config.infra.logs_dir
    logs_dir = Path(config.infra.logs_dir)
    sqlite_path = Path(config.infra.sqlite_path)
    try:
        write_manifest(manifest, logs_dir=logs_dir, sqlite_path=sqlite_path)
    except Exception:
        # If SQLite isn't initialised yet (e.g. bare scratch run), write sidecar only
        logs_dir.mkdir(parents=True, exist_ok=True)
        import json
        from datetime import UTC, datetime

        date_dir = logs_dir / datetime.now(UTC).strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        sidecar = date_dir / f"{manifest.run_id}.manifest.json"
        sidecar.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))

    configure_logging(run_id=manifest.run_id, tier="brain", logs_dir=logs_dir)
    log = structlog.get_logger("ingester.cli")

    log.info("ingester.cli.start", kind=args.kind, src=str(args.src), out=str(args.out))

    out_root = args.out
    result: object

    if args.kind == "market_trades":
        if not args.market_id:
            p.error("--market-id is required for --kind market_trades")
        result = ingest_market_trades(args.src, args.market_id, out_root)

    elif args.kind == "order_book_raw":
        if not args.market_id:
            p.error("--market-id is required for --kind order_book_raw")
        result = ingest_order_book_raw(args.src, args.market_id, out_root)

    elif args.kind == "order_book_combined":
        if not args.market_id or not args.tick_size:
            p.error("--market-id and --tick-size are required for --kind order_book_combined")
        result = ingest_order_book_combined(args.src, args.market_id, args.tick_size, out_root)

    elif args.kind == "underlying_apr":
        if not args.exchange:
            p.error("--exchange is required for --kind underlying_apr")
        result = ingest_underlying_apr(args.src, args.exchange, out_root)

    elif args.kind == "settlement_md":
        if not args.market_id:
            p.error("--market-id is required for --kind settlement_md")
        result = ingest_settlement_md(args.src, args.market_data_src, args.market_id, out_root)

    else:
        raise ValueError(f"unknown kind: {args.kind}")  # unreachable — argparse enforces choices

    print(f"ingested kind={args.kind} result={result}")
    log.info("ingester.cli.done", kind=args.kind, result=str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
