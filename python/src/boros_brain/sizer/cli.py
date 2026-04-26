"""CLI entry point for the sizer (REWARD-03/04 operator surface).

Subcommands: target.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as the first log record before
any subcommand executes. tier='sizer'.

Exit codes:
    0 — success
    1 — domain error (InsufficientCollateralError / FillModelNoFreshFitError /
        FillModelStaleFeatureError / LossModelNoFreshGridError)
    2 — ConfigError (bad or missing config YAML) or Pydantic ValidationError

[[sizing-optimizer-sub-cap-regime-v05]]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.sizer",
        description="Sizing optimizer CLI (REWARD-03/04)",
    )
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to strategy YAML",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # target subcommand: compute q_me_target and print as JSON
    tgt_p = sub.add_parser(
        "target",
        help=(
            "Compute Sizer.q_me_target() for a (market, side) and print "
            "JSON to stdout. NOTE: staleness checks use wall-clock time "
            "(chain_time not initialised in CLI); results may be inaccurate "
            "under clock skew. Operator-diagnostic only."
        ),
    )
    tgt_p.add_argument("--market", required=True, help="market_id")
    tgt_p.add_argument("--side", required=True, choices=["long", "short"], help="long or short")
    tgt_p.add_argument("--depth", type=int, default=5, help="depth_from_mark_ticks (default 5)")
    tgt_p.add_argument(
        "--queue-ahead-wei",
        type=int,
        default=0,
        help="queue_ahead_wei from QueueTracker (default 0)",
    )
    tgt_p.add_argument(
        "--tau-s",
        type=int,
        default=30 * 86400,
        help="time_to_maturity_s (default 30 days)",
    )
    tgt_p.add_argument(
        "--time-to-epoch-end-s",
        type=float,
        default=3600.0,
        help="time_to_epoch_end_s (default 1 hour)",
    )
    tgt_p.add_argument(
        "--sigma-others-pendle",
        type=float,
        default=60.0,
        help="Σ_others in PENDLE-units (default 60.0)",
    )
    tgt_p.add_argument(
        "--e-liq-pendle",
        type=float,
        default=273.0,
        help="E_liq_per_epoch_pendle (default 273.0 — ETHUSDT-29MAY2026 anchor)",
    )
    tgt_p.add_argument(
        "--side-split",
        type=float,
        default=0.86,
        help="side_split fraction (default 0.86 — ETHUSDT-29MAY2026 short)",
    )
    tgt_p.add_argument(
        "--features-json",
        default=None,
        help="JSON dict of fill_model covariate features (default zeros)",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    """Sizer CLI entry point."""
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

    # MANIFEST-FIRST (PROTO-01).
    manifest = build_run_manifest(config)
    sqlite_path = Path(config.infra.sqlite_path)

    configure_logging(
        run_id=manifest.run_id,
        tier="sizer",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(manifest, logs_dir=config.infra.logs_dir, sqlite_path=sqlite_path)
    log = structlog.get_logger("sizer.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump())
    log.info("sizer.cli_started", subcommand=args.cmd)

    try:
        if args.cmd == "target":
            from ..fill_model.predict import (
                FillModelNoFreshFitError,
                FillModelStaleFeatureError,
            )
            from ..loss_model.expected_loss import LossModelNoFreshGridError
            from .optimizer import q_me_target
            from .schemas import InsufficientCollateralError, SizerInput

            # Build features dict — default to zero-filled fill_model whitelist.
            if args.features_json is not None:
                feats = json.loads(args.features_json)
            else:
                feats = {name: 0.0 for name in config.fill_model.covariate_whitelist}

            req = SizerInput(
                market_id=args.market,
                side=args.side,
                depth_from_mark_ticks=args.depth,
                time_to_epoch_end_s=args.time_to_epoch_end_s,
                time_to_maturity_s=args.tau_s,
                queue_ahead_wei=args.queue_ahead_wei,
                current_features=feats,
                # CLI-only: chain_time not initialised here. Wall-clock is an
                # approximation; staleness checks may be wrong under clock skew.
                # Operator-diagnostic only — not used by the 1 Hz decision loop.
                current_chain_ts=int(datetime.now(UTC).timestamp()),
                sigma_others_pendle=args.sigma_others_pendle,
                e_liq_per_epoch_pendle=args.e_liq_pendle,
                side_split=args.side_split,
                t_frac=1.0,
            )

            try:
                out = q_me_target(req, sqlite_path=sqlite_path, config=config)
            except (
                InsufficientCollateralError,
                FillModelNoFreshFitError,
                FillModelStaleFeatureError,
                LossModelNoFreshGridError,
            ) as exc:
                print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
                log.exception("sizer.cli_domain_error", cmd=args.cmd, err=str(exc))
                return 1

            print(json.dumps(out.model_dump(), indent=2))
            return 0

        parser.print_help()
        return 2

    except ValueError as exc:
        # Pydantic ValidationError inherits from ValueError.
        log.exception("sizer.cli_validation_error", cmd=args.cmd, err=str(exc))
        print(f"ValidationError: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "ValidationError" in type(exc).__name__:
            print(f"ValidationError: {msg}", file=sys.stderr)
            log.exception("sizer.cli_validation_error", cmd=args.cmd, err=msg)
            return 2
        log.exception("sizer.cli_error", cmd=args.cmd, err=msg)
        return 1


if __name__ == "__main__":
    sys.exit(main())
