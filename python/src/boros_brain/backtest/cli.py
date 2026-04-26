"""CLI entry point for the backtest engine (BACK-01..08, Phase 5).

Subcommands: run, plot.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as first log record + sidecar
JSON before any subcommand executes. tier='backtest-cli'. Bootstrap RNG seed
is derived from manifest.run_id (ULID tail) → bit-for-bit reproducibility
(Plan 05-07 invariant).

Exit codes:
    0  -- success / ship-gate passes
    1  -- ship-gate fails (5th-pct < alt_yield + all_fees) — kill-report written
    2  -- unrecognised subcommand / config error

[[backtest-replay-engine-v05]]
[[backtest-ship-gate-threshold-assembly]]
[[backtest-cli-and-run-manifest-emission]]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..manifest.schema import RunManifest

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    """Build the backtest CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.backtest",
        description="Event-driven backtest + ship-gate (BACK-01..08)",
    )
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to BotConfig YAML (PROTO-04 SSoT).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run full backtest grid + ship-gate verdict.")
    run_p.add_argument("--market", required=True, help="market_id")
    run_p.add_argument("--side", required=True, choices=["long", "short"])

    plot_p = sub.add_parser("plot", help="Re-render plots from existing run_id parquet output.")
    plot_p.add_argument("--run-id", required=True, help="ULID of an existing run")
    return p


async def _dispatch_run(args: argparse.Namespace, config: BotConfig, manifest: RunManifest) -> int:
    """Run subcommand: orchestrate baseline replay + 4 sweeps + ship-gate verdict.

    Each sweep / grid call passes parent_manifest=manifest so child runs carry
    parent_run_id (PROTO-01 mid-run knob-change semantics — D2 anti-pattern guard).
    """
    from .contour_2d import contour_grid_to_parquet, run_2d_contour_grid
    from .perturbation import ReplayInputs, run_perturbation_grid
    from .replay import ReplayEngine
    from .report import (
        append_perturbation_section_to_ship_gate_report,
        write_backtest_row,
        write_ship_gate_verdict_json,
    )
    from .schemas import ReplayConfig
    from .ship_gate import (
        ShipGateHalt,
        evaluate_ship_gate,
        write_ship_gate_report,
    )
    from .sweeps.cancel_latency import run_cancel_latency_sweep
    from .sweeps.competition import run_competition_sweep
    from .sweeps.forfeit_branch import run_forfeit_branch_sweep

    log = structlog.get_logger("backtest.cli")

    parquet_root = Path(config.backtest.output_parquet_root)
    replay_inputs = ReplayInputs(
        market_id=args.market,
        side=args.side,
        parquet_root=parquet_root,
        sqlite_path=Path(config.infra.sqlite_path),
        cancel_latency_s=float(config.execution.cancel_latency_budget_s),
        voluntary_cancel_branch="benign",
        sigma_others_multiplier=1.0,
    )
    base_replay_cfg = ReplayConfig(
        config=config,
        market_id=args.market,
        side=args.side,
        parquet_root=parquet_root,
        sqlite_path=Path(config.infra.sqlite_path),
        cancel_latency_s=float(config.execution.cancel_latency_budget_s),
        voluntary_cancel_branch="benign",
        sigma_others_multiplier=1.0,
    )

    log.info("backtest.run.baseline_start")
    base_engine = ReplayEngine(
        config=config,
        market_id=args.market,
        side=args.side,
        parquet_root=parquet_root,
        sqlite_path=Path(config.infra.sqlite_path),
        cancel_latency_s=float(config.execution.cancel_latency_budget_s),
        run_id=manifest.run_id,
        manifest=manifest,
        replay_config=base_replay_cfg,
    )
    base_result = await base_engine.run()
    for row in base_result.rows:
        write_backtest_row(row, parquet_root=parquet_root)

    log.info("backtest.run.cancel_latency_sweep_start")
    await run_cancel_latency_sweep(base_replay_cfg, parent_manifest=manifest, config=config)

    log.info("backtest.run.competition_sweep_start")
    await run_competition_sweep(base_replay_cfg, parent_manifest=manifest, config=config)

    log.info("backtest.run.forfeit_branch_sweep_start")
    await run_forfeit_branch_sweep(base_replay_cfg, parent_manifest=manifest, config=config)

    log.info("backtest.run.perturbation_grid_start")
    perturbation_rows = await run_perturbation_grid(
        config,
        replay_inputs,
        parent_manifest=manifest,
        n_resamples=config.backtest.bootstrap_n_resamples,
    )

    log.info("backtest.run.contour_2d_start")
    grid = await run_2d_contour_grid(
        config,
        replay_inputs,
        parent_manifest=manifest,
        grid_size=5,
    )
    knob_a, knob_b = config.backtest.contour_2d_knobs[:2]
    contour_grid_to_parquet(
        grid,
        run_id=manifest.run_id,
        knob_a_path=knob_a,
        knob_b_path=knob_b,
        parquet_root=parquet_root,
    )

    log.info("backtest.run.ship_gate_evaluate")
    verdict = evaluate_ship_gate(
        base_result.daily_pnl,
        manifest=manifest,
        config=config,
    )
    write_ship_gate_verdict_json(verdict, parquet_root=parquet_root)
    output_dir = Path("var/backtest") / manifest.run_id
    report_path = write_ship_gate_report(
        verdict,
        config=config,
        manifest=manifest,
        output_dir=output_dir,
    )
    append_perturbation_section_to_ship_gate_report(report_path, perturbation_rows)

    log.info(
        "backtest.run.complete",
        passed=verdict.passed,
        p5=verdict.p5_annualized_pnl,
        threshold=verdict.threshold,
    )
    if not verdict.passed:
        raise ShipGateHalt(1)
    return 0


def _dispatch_plot(args: argparse.Namespace, config: BotConfig, manifest: RunManifest) -> int:
    """Plot subcommand: re-render plots from existing run_id parquet output."""
    import json

    import polars as pl

    from .report import plot_calibration

    log = structlog.get_logger("backtest.cli")
    parquet_root = Path(config.backtest.output_parquet_root)
    sidecar = Path("var/backtest") / args.run_id / f"{args.run_id}.manifest.json"
    if not sidecar.exists():
        log.error("backtest.plot.sidecar_missing", path=str(sidecar))
        print(f"manifest sidecar not found: {sidecar}", file=sys.stderr)
        return 2
    json.loads(sidecar.read_text())  # validates JSON; future use for plot subtitles

    rows_glob = parquet_root / f"run_id={args.run_id}" / "**" / "*.parquet"
    log.info("backtest.plot.load_rows", glob=str(rows_glob))
    df = pl.read_parquet(str(rows_glob))
    rows = df.to_dicts()
    plots_dir = Path("var/backtest") / args.run_id / "plots"
    plot_calibration(rows, out_path=plots_dir / "calibration.png")
    # dP&L/dL and dP&L/dQ slope tuples are reconstructed from sweep_axis-filtered rows
    # (out of scope for this smoke; smoke test calls plot_calibration only).
    return 0


def main(argv: list[str] | None = None) -> int:
    """Backtest engine CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    from ..config.loader import load_config
    from ..logging.structlog_setup import configure_logging
    from ..manifest.writer import build_run_manifest, write_manifest
    from .run_manifest import emit_backtest_manifest

    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"ConfigError: {exc}", file=sys.stderr)
        return 2

    # MANIFEST-FIRST (PROTO-01) — 4-step preamble copied verbatim from
    # decision/cli.py:85-99, only tier name changed.
    manifest = build_run_manifest(config)
    configure_logging(
        run_id=manifest.run_id,
        tier="backtest-cli",
        logs_dir=Path(config.infra.logs_dir),
    )
    write_manifest(
        manifest,
        logs_dir=Path(config.infra.logs_dir),
        sqlite_path=Path(config.infra.sqlite_path),
    )
    emit_backtest_manifest(
        manifest,
        run_id=manifest.run_id,
        output_dir=Path("var/backtest") / manifest.run_id,
    )
    log = structlog.get_logger("backtest.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))
    log.info("backtest.cli_started", subcommand=args.cmd)

    if args.cmd == "run":
        return asyncio.run(_dispatch_run(args, config, manifest))
    if args.cmd == "plot":
        return _dispatch_plot(args, config, manifest)
    print(f"unrecognised subcommand: {args.cmd}", file=sys.stderr)
    return 2
