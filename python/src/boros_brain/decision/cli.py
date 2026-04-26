"""CLI entry point for the decision engine (Plan 04-06).

Subcommands: predeploy-gate, reset-breaker.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as first log record before any
subcommand executes. tier='decision-cli'.

Exit codes:
    0  -- success / gate passes
    1  -- gate fails / screener error
    2  -- unrecognised subcommand / config error

[[predeploy-gate-cli]]: predeploy-gate subcommand spec and Pitfall #8
[[breaker-coordinator-kill-mutex]]: reset-breaker context
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    """Build the decision CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.decision",
        description="Decision engine CLI (predeploy_gate, reset_breaker)",
    )
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to BotConfig YAML (PROTO-04 SSoT).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "predeploy-gate",
        help="Re-run economics gate; write predeploy_gate_records row + wiki page. Exit 0=pass, 1=fail.",
    )

    rst = sub.add_parser(
        "reset-breaker",
        help="Manually clear a tripped breaker (insert rearmed row in breaker_events).",
    )
    rst.add_argument(
        "--name",
        required=True,
        choices=[
            "margin_trajectory",
            "oracle_stale",
            "clo_removal",
            "clo_shift",
            "fill_rate",
            "competition",
            "maturity",
            "side_budget",
            "underlying_stale",
            "loss_fit_degraded",
        ],
        help="Name of the breaker to reset.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Decision engine CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    from ..config.loader import load_config
    from ..logging.structlog_setup import configure_logging
    from ..manifest.writer import build_run_manifest, write_manifest

    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"ConfigError: {exc}", file=sys.stderr)
        return 2

    # MANIFEST-FIRST (PROTO-01)
    manifest = build_run_manifest(config)
    configure_logging(
        run_id=manifest.run_id,
        tier="decision-cli",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(
        manifest,
        logs_dir=config.infra.logs_dir,
        sqlite_path=config.infra.sqlite_path,
    )
    log = structlog.get_logger("decision.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))
    log.info("decision.cli_started", subcommand=args.cmd)

    try:
        if args.cmd == "predeploy-gate":
            from .predeploy_gate import run_predeploy_gate

            return run_predeploy_gate(
                config,
                sqlite_path=Path(config.infra.sqlite_path),
                run_id=manifest.run_id,
            )

        if args.cmd == "reset-breaker":
            return _reset_breaker(config, args.name, manifest.run_id)

    except Exception as exc:  # noqa: BLE001
        log.exception("decision.cli_error", cmd=args.cmd, err=str(exc))
        return 1

    parser.print_help()
    return 2


def _reset_breaker(config: object, breaker_name: str, run_id: str) -> int:
    """Manually clear a tripped breaker by inserting a rearmed row.

    v0.5 minimal — Phase 6+ may extend with full state reconciliation.
    The operator uses this after manually resolving the underlying condition
    that triggered the breaker (e.g., after oracle feed is restored).
    """
    from pathlib import Path

    import structlog

    from ..state.db import open_connection
    from ..state.writers.breaker_events import insert_breaker_event

    log = structlog.get_logger("decision.cli.reset_breaker")
    sqlite_path = Path(config.infra.sqlite_path)  # type: ignore[attr-defined]

    from datetime import UTC, datetime

    # CLI-only: chain_time RPC is not initialised in CLI context. Wall-clock is an
    # approximation acceptable for operator diagnostics (acknowledged deviation from
    # INFRA-14, same as fill_model/cli.py pattern).
    chain_ts = int(datetime.now(UTC).timestamp())

    with open_connection(sqlite_path) as conn:
        insert_breaker_event(
            conn,
            kind="rearmed",
            breaker_name=breaker_name,
            reason="manual_operator_reset",
            chain_ts=chain_ts,
            run_id=run_id,
        )
        conn.commit()

    log.info(
        "decision.breaker_reset",
        breaker_name=breaker_name,
        run_id=run_id,
    )
    return 0
