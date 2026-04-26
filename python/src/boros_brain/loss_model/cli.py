"""CLI entry point for the loss model (LOSS-01/02/03 operator surface).

Subcommands: fit, expected-loss, force-degrade.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as first log record before any
subcommand executes. tier='loss_model'.

Exit codes:
    0  -- success
    1  -- LossModelNoFreshGridError (no grid persisted; expected-loss subcommand)
    2  -- ConfigError (bad or missing config YAML)

[[empirical-loss-grid-v05]]
[[fee-cost-term-in-expected-loss]]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.loss_model",
        description="Loss model CLI (LOSS-01/02/03)",
    )
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to strategy YAML",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "fit",
        help="Run a single synchronous loss-grid refit across config.markets",
    )

    el_p = sub.add_parser(
        "expected-loss",
        help=(
            "Run expected_loss() against latest grid; print JSON to stdout. "
            "NOTE: staleness check uses wall-clock time (chain_time not "
            "initialised in CLI); results may be inaccurate under clock skew."
        ),
    )
    el_p.add_argument("--market", required=True, help="market_id")
    el_p.add_argument("--side", required=True, choices=["long", "short"])
    el_p.add_argument("--depth", type=int, default=5, help="depth_from_mark_ticks")
    el_p.add_argument(
        "--tau-s",
        type=int,
        default=30 * 86400,
        help="time_to_maturity_s (default 30 days)",
    )

    sub.add_parser(
        "force-degrade",
        help=("Inject sparse-data scenario → fit_status='degraded' guaranteed " "(Plan 03-01 smoke)"),
    )

    return p


def main(argv: list[str] | None = None) -> int:
    """Loss model CLI entry point."""
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
        tier="loss_model",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(
        manifest,
        logs_dir=config.infra.logs_dir,
        sqlite_path=config.infra.sqlite_path,
    )
    log = structlog.get_logger("loss_model.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump())
    log.info("loss_model.cli_started", subcommand=args.cmd)

    try:
        if args.cmd == "fit":
            from .refit_loop import refit_once

            asyncio.run(refit_once(config, manifest.run_id))
            return 0

        if args.cmd == "expected-loss":
            from .expected_loss import (
                LossModelNoFreshGridError,
                expected_loss,
            )
            from .schemas import ExpectedLossInput

            req = ExpectedLossInput(
                market_id=args.market,
                side=args.side,
                depth_from_mark_ticks=args.depth,
                time_to_maturity_s=args.tau_s,
                # CLI-only: chain_time not initialised here (no RPC). Wall-clock
                # is an approximation; staleness check may be wrong under clock
                # skew. Acceptable for operator diagnostics — not used by the
                # 1 Hz decision loop. (INFRA-14 acknowledged deviation.)
                current_chain_ts=int(datetime.now(UTC).timestamp()),
            )
            try:
                out = expected_loss(
                    req,
                    sqlite_path=Path(config.infra.sqlite_path),
                    config=config,
                )
            except LossModelNoFreshGridError as exc:
                print(f"LossModelNoFreshGridError: {exc}", file=sys.stderr)
                return 1
            print(json.dumps(out.model_dump(), indent=2))
            return 0

        if args.cmd == "force-degrade":
            # Persist a fit_status='degraded' artifact for testing the downstream
            # PLACE-suppression path (P3-9). No fills; replay short-circuits;
            # build_loss_grid_artifact_from_fills emits degraded with empty cells.
            from .artifact import write_loss_grid_artifact
            from .fit import build_loss_grid_artifact_from_fills

            market_id = config.markets[0].market_id if config.markets else "TEST-MARKET"
            artifact = build_loss_grid_artifact_from_fills(
                fills=[],
                config=config,
                market_id=market_id,
                side="long",
                window_start_ts=0,
                window_end_ts=0,
                run_id=manifest.run_id,
            )
            write_loss_grid_artifact(artifact, sqlite_path=Path(config.infra.sqlite_path))
            log.info("loss_model.force_degrade_complete", run_id=manifest.run_id)
            return 0

        parser.print_help()
        return 2

    except Exception as exc:  # noqa: BLE001
        try:
            from .expected_loss import LossModelNoFreshGridError

            if isinstance(exc, LossModelNoFreshGridError):
                log.exception("loss_model.cli_error", cmd=args.cmd, err=str(exc))
                return 1
        except ImportError:
            pass
        log.exception("loss_model.cli_error", cmd=args.cmd, err=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
