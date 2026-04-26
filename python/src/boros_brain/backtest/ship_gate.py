"""BACK-07: ship-gate verdict + threshold assembly.

5th-percentile annualized P&L from N=2000 bootstrap resamples must exceed
alt_yield + all_fees to ship. Point-estimate above threshold is INSUFFICIENT
(PITFALLS §B7).

Mirrors screener.economics_gate halt-on-empty discipline + screener.kill_report
template-rendered Markdown halt artifact.

[[backtest-ship-gate-threshold-assembly]]
[[backtest-bootstrap-methodology-v05]]
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import structlog

from ..config.schema import BotConfig
from ..manifest.schema import RunManifest
from .bootstrap import block_bootstrap_pnl, make_rng, seed_from_manifest
from .schemas import ShipGateVerdict, ThresholdComponents

log = structlog.get_logger(__name__)


class ShipGateHalt(SystemExit):
    """Phase 5 ship-gate fail. CLI converts to exit code 1.

    Inherits SystemExit so bare `except Exception` does NOT swallow it. Mirrors
    screener.economics_gate.ProjectHalt verbatim.
    """


def assemble_threshold(config: BotConfig) -> ThresholdComponents:
    """Per BACK-07: alt_yield (config.screener.alt_yield) + all_fees (config.backtest.all_fees_threshold).

    Both are decimal-fraction APRs. Components persisted to ship_gate_verdict.json
    so operator can audit alongside the verdict.
    """
    alt = float(config.screener.alt_yield)
    fees = float(config.backtest.all_fees_threshold)
    return ThresholdComponents(
        alternative_yield=alt,
        all_fees=fees,
        total=alt + fees,
        components={"alt_yield": alt, "all_fees": fees},
    )


def evaluate_ship_gate(
    daily_pnl: np.ndarray,
    *,
    manifest: RunManifest,
    config: BotConfig,
) -> ShipGateVerdict:
    """Run block bootstrap + 5th-pct comparison.

    Note: this function does NOT raise ShipGateHalt — the caller (CLI in Plan 05-09)
    inspects verdict.passed and raises if False. evaluate_ship_gate stays pure
    (no I/O, no halt) so it's testable in isolation.
    """
    rng = make_rng(manifest)
    resampled = block_bootstrap_pnl(
        daily_pnl,
        rng=rng,
        n_resamples=config.backtest.bootstrap_n_resamples,
    )
    p5 = float(np.percentile(resampled, 5))
    threshold = assemble_threshold(config).total
    seed = seed_from_manifest(manifest)
    return ShipGateVerdict(
        p5_annualized_pnl=p5,
        threshold=threshold,
        passed=(p5 > threshold),
        n_resamples=config.backtest.bootstrap_n_resamples,
        block_seconds=config.backtest.bootstrap_block_seconds,
        seed=seed,
        manifest_run_id=manifest.run_id,
    )


def write_ship_gate_report(
    verdict: ShipGateVerdict,
    *,
    config: BotConfig,
    manifest: RunManifest,
    output_dir: Path | None = None,
) -> Path:
    """Write ship-gate-report.md. Mirrors kill_report.write_kill_report:
    timestamp + git_sha + run_id + threshold + full knob tree as JSON.

    Default output_dir = var/backtest/<run_id>/ (matches RESEARCH §"Validation Architecture").
    """
    today = datetime.now(UTC)
    if output_dir is None:
        output_dir = Path("var/backtest") / verdict.manifest_run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "ship-gate-report.md"

    try:
        git_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_sha = "unknown"

    threshold_components = assemble_threshold(config)

    status_str = "PASSED" if verdict.passed else "FAILED"
    body = (
        f"# Phase 5 Ship-Gate Verdict\n\n"
        f"**Status:** {status_str}\n\n"
        f"**Run ID:** `{verdict.manifest_run_id}`\n"
        f"**Git SHA:** `{git_sha}`\n"
        f"**Timestamp:** `{today.isoformat()}`\n\n"
        f"## Verdict\n\n"
        f"- 5th-percentile annualized P&L: **{verdict.p5_annualized_pnl:.4f}**"
        f" ({verdict.p5_annualized_pnl * 100:.2f}% APR)\n"
        f"- Threshold (alt_yield + all_fees): **{verdict.threshold:.4f}**"
        f" ({verdict.threshold * 100:.2f}% APR)\n"
        f"- Bootstrap resamples: `{verdict.n_resamples}`\n"
        f"- Block length (seconds): `{verdict.block_seconds}`\n"
        f"- RNG seed (manifest-derived): `{verdict.seed}`\n\n"
        f"## Threshold Components\n\n"
        f"| Component | Value |\n"
        f"|-----------|-------|\n"
        f"| `screener.alt_yield` | {threshold_components.alternative_yield:.4f} |\n"
        f"| `backtest.all_fees_threshold` | {threshold_components.all_fees:.4f} |\n"
        f"| **Total** | **{threshold_components.total:.4f}** |\n\n"
        f"## RUN_MANIFEST excerpt\n\n"
        f"- `mode`: `{manifest.mode}`\n"
        f"- `git_sha`: `{manifest.git_sha}`\n"
        f"- `git_dirty`: `{manifest.git_dirty}`\n"
        f"- `strategy_version`: `{manifest.strategy_version}`\n"
        f"- `market_id`: `{manifest.market_id}`\n"
        f"- `side`: `{manifest.side}`\n\n"
        f"## Full Knob Tree (BotConfig.model_dump)\n\n"
        f"```json\n{json.dumps(config.model_dump(mode='json'), indent=2)}\n```\n"
    )
    out.write_text(body)
    log.info("ship_gate.report_written", path=str(out), passed=verdict.passed)
    return out


__all__ = [
    "ShipGateHalt",
    "assemble_threshold",
    "evaluate_ship_gate",
    "write_ship_gate_report",
]
