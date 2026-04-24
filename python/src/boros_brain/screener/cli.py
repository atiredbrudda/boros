"""python -m boros_brain.screener CLI entrypoint (DATA-08).

Produces ``var/reports/screener_metrics.json``. NON-HALTING: an empty shortlist
is allowed here — DATA-09 (plan 01-12) is the economics kill-switch gate.

Usage::

    python -m boros_brain.screener --run --config strategy/v0.5-default.yaml

RUN_MANIFEST is emitted as the first log record (PROTO-01 / INFRA-06).
"""

from __future__ import annotations

import argparse
import sys

import structlog

log = structlog.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Screener CLI entry point.

    Returns
    -------
    int
        Exit code: 0 on success (empty shortlist is still success — DATA-09
        is the halting gate).
    """
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.screener",
        description=(
            "DATA-08 market screener. Evaluates candidate markets on 6 filter "
            "criteria and writes var/reports/screener_metrics.json."
        ),
    )
    p.add_argument("--run", action="store_true", help="Execute the screener")
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to BotConfig YAML (default: strategy/v0.5-default.yaml)",
    )
    p.add_argument(
        "--markets",
        nargs="+",
        help="Override the market list from config",
        default=None,
    )
    p.add_argument(
        "--out",
        default="var/reports/screener_metrics.json",
        help="Output path for screener_metrics.json",
    )
    args = p.parse_args(argv)

    if not args.run:
        # Informational print only — no screener run
        log.info("screener.cli", status="idle", hint="pass --run to execute")
        return 0

    # Lazy imports to keep --help fast and avoid import errors when config/DuckDB
    # is not available (e.g., in test environments that only test --help).
    from ..config.loader import load_config
    from ..duckdb_layer.setup import open_analytical_conn
    from ..logging.structlog_setup import configure_logging
    from ..manifest.writer import build_run_manifest, write_manifest
    from .filter import apply_screener_filters
    from .report import write_screener_metrics_report

    config = load_config(args.config)

    # PROTO-01: RUN_MANIFEST emitted FIRST — build manifest before configure_logging
    # so we have a run_id to pass as the log-file stem.
    manifest = build_run_manifest(config)
    configure_logging(
        run_id=manifest.run_id,
        tier="screener",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(
        manifest,
        logs_dir=config.infra.logs_dir,
        sqlite_path=config.infra.sqlite_path,
    )

    conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")
    market_ids = args.markets or [m.market_id for m in config.markets]

    results = apply_screener_filters(market_ids, conn, config)
    write_screener_metrics_report(results, out=args.out)

    shortlist = [r.market_id for r in results if r.filter_pass][:4]
    log.info("screener.complete", shortlist=shortlist, out=args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
