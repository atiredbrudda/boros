"""python -m boros_brain.screener CLI entrypoint (DATA-08 + DATA-09).

Produces ``var/reports/screener_metrics.json`` (DATA-08) and optionally runs the
DATA-09 economics kill-switch gate (--economics-gate).

Usage::

    python -m boros_brain.screener --run --config strategy/v0.5-default.yaml
    python -m boros_brain.screener --economics-gate --config strategy/v0.5-default.yaml
    python -m boros_brain.screener --economics-gate --config strategy/v0.5-default.yaml \\
        --metrics var/reports/screener_metrics.json

Exit codes:
    0  -- success (DATA-08 always; DATA-09 when shortlist is non-empty)
    1  -- DATA-09 ProjectHalt (empty shortlist after economics gate)
    2  -- ConfigError (missing or out-of-range knob in config YAML)

RUN_MANIFEST is emitted as the first log record (PROTO-01 / INFRA-06).
"""

from __future__ import annotations

import argparse
import sys

import structlog

log = structlog.get_logger(__name__)


def run_screener(
    config: object, *, markets: list[str] | None = None, out: str = "var/reports/screener_metrics.json"
) -> None:
    """Programmatic screener runner (DATA-08). Called by rescreen.py."""
    from ..duckdb_layer.setup import open_analytical_conn
    from .filter import apply_screener_filters
    from .report import write_screener_metrics_report

    conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")  # type: ignore[attr-defined]
    market_ids = markets or [m.market_id for m in config.markets]  # type: ignore[attr-defined]

    results = apply_screener_filters(market_ids, conn, config)
    write_screener_metrics_report(results, out=out)

    shortlist = [r.market_id for r in results if r.filter_pass][:4]
    log.info("screener.complete", shortlist=shortlist, out=out)


def main(argv: list[str] | None = None) -> int:
    """Screener CLI entry point.

    Returns
    -------
    int
        Exit code: 0 on success (DATA-08 empty shortlist is OK -- DATA-09 is the
        halting gate). 1 on ProjectHalt (DATA-09). 2 on ConfigError.
    """
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.screener",
        description=(
            "DATA-08 market screener + DATA-09 economics kill-switch. "
            "Evaluates candidate markets on 6 filter criteria and writes "
            "var/reports/screener_metrics.json. Optionally runs the economics gate."
        ),
    )
    p.add_argument("--run", action="store_true", help="Execute the DATA-08 screener")
    p.add_argument(
        "--economics-gate",
        action="store_true",
        dest="economics_gate",
        help="Run DATA-09 economics kill-switch after screener (or standalone with --metrics)",
    )
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
    p.add_argument(
        "--metrics",
        default="var/reports/screener_metrics.json",
        dest="metrics_path",
        help="Path to screener_metrics.json for --economics-gate (default: var/reports/screener_metrics.json)",
    )
    args = p.parse_args(argv)

    if not args.run and not args.economics_gate:
        # Informational print only -- no screener run
        log.info("screener.cli", status="idle", hint="pass --run or --economics-gate to execute")
        return 0

    # Lazy imports to keep --help fast and avoid import errors when config/DuckDB
    # is not available (e.g., in test environments that only test --help).
    from ..config.loader import load_config
    from ..logging.structlog_setup import configure_logging
    from ..manifest.writer import build_run_manifest, write_manifest

    config = load_config(args.config)

    # PROTO-01: RUN_MANIFEST emitted FIRST -- build manifest before configure_logging
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

    if args.run:
        run_screener(config, markets=args.markets, out=args.out)

    if args.economics_gate:
        from .economics_gate import ConfigError, ProjectHalt, run_economics_gate

        try:
            shortlist = run_economics_gate(args.config, args.metrics_path)
            log.info("economics_gate.cli.pass", shortlist=shortlist)
            return 0
        except ConfigError as exc:
            log.error("economics_gate.config_error", error=str(exc))
            return 2
        except ProjectHalt:
            # ProjectHalt already wrote the kill-report; exit 1
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
