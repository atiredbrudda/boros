"""CLI entry point for the fill model (FILL-01/05/06 operator surface).

Subcommands: fit, predict, calibration-report, force-degrade.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as first log record before any
subcommand executes. tier='fill_model'.

Exit codes:
    0  -- success
    1  -- FillModelNoFreshFitError (no fit persisted; predict subcommand)
    2  -- ConfigError (bad or missing config YAML)

[[rolling-14-day-refit-cadence-and-staleness]]
[[fill-model-goodness-of-fit-rosenblatt-time-change]]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import structlog

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.fill_model",
        description="Fill model CLI (FILL-01/05/06)",
    )
    p.add_argument("--config", default="strategy/v0.5-default.yaml", help="Path to strategy YAML")
    sub = p.add_subparsers(dest="cmd", required=True)

    fit_p = sub.add_parser("fit", help="Run a single synchronous refit across config.markets")
    fit_p.add_argument("--market", required=False, default=None, help="Specific market_id to fit")
    fit_p.add_argument("--side", required=False, default=None, choices=["long", "short"])

    pred_p = sub.add_parser("predict", help="Run predict() against latest fit; print JSON to stdout")
    pred_p.add_argument("--market", required=True, help="market_id")
    pred_p.add_argument("--side", required=True, choices=["long", "short"])
    pred_p.add_argument("--depth", type=int, default=5, help="depth_from_mark_ticks")

    sub.add_parser("calibration-report", help="Aggregate fill_model_fits into JSON + Markdown rollup")

    sub.add_parser(
        "force-degrade",
        help=(
            "Inject synthetic sparse data → fit_degraded → smoke the full logging path "
            "(Success Criterion #4)"
        ),
    )

    return p


def main(argv: list[str] | None = None) -> int:
    """Fill model CLI entry point."""
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
        tier="fill_model",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(manifest, logs_dir=config.infra.logs_dir, sqlite_path=config.infra.sqlite_path)
    log = structlog.get_logger("fill_model.cli")
    log.info("fill_model.cli_started", subcommand=args.cmd)

    try:
        if args.cmd == "fit":
            from .refit_loop import refit_once
            asyncio.run(refit_once(config, manifest.run_id))
            return 0

        if args.cmd == "predict":
            from .predict import FillModelNoFreshFitError, PredictInput, predict
            from ..state.writers.fill_model_fits import get_latest_fit
            fit = get_latest_fit(Path(config.infra.sqlite_path), args.market, args.side)
            if fit is None:
                print("FillModelNoFreshFitError: no fit exists", file=sys.stderr)
                return 1
            feats = {name: 0.0 for name in fit.covariate_whitelist}
            req = PredictInput(
                market_id=args.market, side=args.side,
                depth_from_mark_ticks=args.depth, queue_ahead_wei=0,
                current_features=feats, time_to_epoch_end_s=3600.0,
                current_chain_ts=int(datetime.now(UTC).timestamp()),
            )
            out = predict(req, sqlite_path=Path(config.infra.sqlite_path), config=config)
            print(json.dumps(out.model_dump(), indent=2))
            return 0

        if args.cmd == "calibration-report":
            from .report import write_fill_model_report
            out_json = Path("var/reports/fill_model_report.json")
            out_md = Path("python/docs/fill_model") / f"calibration-{datetime.now(UTC).strftime('%Y-%m-%d')}.md"
            write_fill_model_report(config, out_json, out_markdown_path=out_md)
            print(f"Written {out_json} + {out_md}")
            return 0

        if args.cmd == "force-degrade":
            # Inject synthetic sparse data → fit_status='degraded' guaranteed.
            # n=15 is below default min_events_per_param_ratio × n_params (10 × 6 = 60).
            from .fit import fit_market_side
            from .report import write_fill_model_report
            n = 15
            market_id = config.markets[0].market_id if config.markets else "TEST-MARKET"
            df = pl.DataFrame({
                "market_id": [market_id] * n,
                "side": ["long"] * n,
                "bin_start": list(range(0, n * 60, 60)),  # artificial integer timestamps
                "trade_count": [0, 1, 0, 2, 1, 0, 0, 1, 2, 0, 1, 0, 0, 1, 2],
                "basis_spread": [0.1] * n,
                "imbalance": [0.0] * n,
                "sin_settlement": [0.0] * n,
                "cos_settlement": [1.0] * n,
                "ewma_vol": [0.1] * n,
                "bin_duration_s": [60.0] * n,
            })
            fit_market_side(
                features_df=df, market_id=market_id, side="long",
                config=config, run_id=manifest.run_id,
                sqlite_path=Path(config.infra.sqlite_path),
            )
            out_json = Path("var/reports/fill_model_report.json")
            write_fill_model_report(config, out_json)
            log.info("fill_model.force_degrade_complete", run_id=manifest.run_id)
            return 0

        parser.print_help()
        return 2

    except Exception as exc:  # noqa: BLE001
        try:
            from .predict import FillModelNoFreshFitError
            if isinstance(exc, FillModelNoFreshFitError):
                log.exception("fill_model.cli_error", cmd=args.cmd, err=str(exc))
                return 1
        except ImportError:
            pass
        log.exception("fill_model.cli_error", cmd=args.cmd, err=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
