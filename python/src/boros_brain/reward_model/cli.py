"""CLI entry point for the reward share model (REWARD-01/02/04 operator surface).

Subcommands: curve, competition-snapshot, calibrate.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as the first log record before
any subcommand executes. tier='reward_model'.

Exit codes:
    0 — success
    1 — domain error (e.g., compute_q_cap unreachable, REST degraded with no fallback row)
    2 — ConfigError or Pydantic ValidationError (e.g., split-sum mismatch)

[[reward-cap-geometry-v05]]
[[market-reward-calibration-operator-workflow]]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.reward_model",
        description="Reward share model CLI (REWARD-01/02/04)",
    )
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to strategy YAML",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # curve subcommand: compute r_capped_curve and print as JSON
    curve_p = sub.add_parser("curve", help="Compute r_capped_curve for a (market, side)")
    curve_p.add_argument("--market", required=True, help="market_id")
    curve_p.add_argument(
        "--side", required=True, choices=["long", "short"], help="long or short"
    )
    curve_p.add_argument("--q-me", type=float, default=0.001, help="Q_me in PENDLE-units")
    curve_p.add_argument(
        "--sigma-others", type=float, default=60.0, help="Σ_others in PENDLE-units"
    )
    curve_p.add_argument(
        "--e-liq-pendle",
        type=float,
        default=273.0,
        help="E_liq_per_epoch_pendle (operator anchor)",
    )
    curve_p.add_argument(
        "--side-split",
        type=float,
        default=0.86,
        help="side_split (long_side_split or short_side_split)",
    )
    curve_p.add_argument(
        "--collateral-usd",
        type=float,
        default=100.0,
        help="Operator collateral USD (default 100)",
    )

    # competition-snapshot subcommand: one-shot tracker cycle
    snap_p = sub.add_parser(
        "competition-snapshot",
        help="One-shot CompetitionTracker.run_one_cycle and print latest row",
    )
    snap_p.add_argument("--market", required=True, help="market_id")

    # calibrate subcommand: operator workflow
    cal_p = sub.add_parser(
        "calibrate",
        help="Persist operator-supplied E_liq + side splits to market_reward_calibration (LOCKED D-01)",
    )
    cal_p.add_argument("--market", required=True, help="market_id")
    cal_p.add_argument(
        "--e-liq-pendle",
        type=float,
        required=True,
        help="E_liq_per_epoch_pendle from Pendle dApp / docs / team",
    )
    cal_p.add_argument("--long-split", type=float, required=True, help="Long-side fraction (0..1)")
    cal_p.add_argument(
        "--short-split", type=float, required=True, help="Short-side fraction (0..1)"
    )
    cal_p.add_argument(
        "--source",
        default="dapp_ui",
        choices=["dapp_ui", "team_statement", "pendle_docs"],
        help="Source enum (LOCKED D-01)",
    )
    cal_p.add_argument(
        "--sqlite-path",
        default=None,
        help="Override config.infra.sqlite_path (test fixtures)",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    """Reward model CLI entry point."""
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
    sqlite_path_str = (
        args.sqlite_path
        if getattr(args, "sqlite_path", None)
        else config.infra.sqlite_path
    )
    sqlite_path = Path(sqlite_path_str)

    configure_logging(
        run_id=manifest.run_id,
        tier="reward_model",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(
        manifest, logs_dir=config.infra.logs_dir, sqlite_path=sqlite_path
    )
    log = structlog.get_logger("reward_model.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump())
    log.info("reward_model.cli_started", subcommand=args.cmd)

    try:
        if args.cmd == "curve":
            from .r_capped import r_capped_curve
            from .schemas import RewardCurveInput

            req = RewardCurveInput(
                market_id=args.market,
                side=args.side,
                q_me_pendle=args.q_me,
                sigma_others_pendle=args.sigma_others,
                e_liq_per_epoch_pendle=args.e_liq_pendle,
                side_split=args.side_split,
                t_frac=1.0,
                collateral_usd=args.collateral_usd,
                pendle_price_usd=config.pricing.pendle_price_usd,
                epoch_days=config.reward_share_model.epoch_days,
            )
            out = r_capped_curve(req)
            print(json.dumps(out.model_dump(), indent=2))
            return 0

        if args.cmd == "competition-snapshot":
            from ..state.writers.competition_history import (
                get_latest_competition,
            )

            row = get_latest_competition(sqlite_path, args.market)
            if row is None:
                print(f"no competition_history row for {args.market}", file=sys.stderr)
                return 1
            print(json.dumps(row, indent=2))
            return 0

        if args.cmd == "calibrate":
            from .calibrate import insert_operator_calibration

            insert_operator_calibration(
                sqlite_path,
                market_id=args.market,
                e_liq_per_epoch_pendle=args.e_liq_pendle,
                long_side_split=args.long_split,
                short_side_split=args.short_split,
                source=args.source,
                run_id=manifest.run_id,
            )
            log.info(
                "reward_model.calibrate_complete",
                market_id=args.market,
                run_id=manifest.run_id,
            )
            return 0

        parser.print_help()
        return 2

    except ValueError as exc:
        # P3-4 split-sum + Pydantic ValidationError both surface as exceptions.
        log.exception("reward_model.cli_validation_error", cmd=args.cmd, err=str(exc))
        print(f"ValidationError: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        # Pydantic ValidationError inherits from ValueError so we catch it above;
        # structural / config-load errors surface here.
        msg = str(exc)
        if "ValidationError" in type(exc).__name__:
            print(f"ValidationError: {msg}", file=sys.stderr)
            log.exception("reward_model.cli_validation_error", cmd=args.cmd, err=msg)
            return 2
        log.exception("reward_model.cli_error", cmd=args.cmd, err=msg)
        return 1


if __name__ == "__main__":
    sys.exit(main())
