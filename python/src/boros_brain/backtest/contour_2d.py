"""BACK-08: 5×5 2D contour grid on the two operator-chosen knobs.

Default knobs per BotConfig.backtest.contour_2d_knobs (RESEARCH L1049-1053):
  ("execution.cancel_latency_budget_s", "screener.alt_yield")

Rationale:
  - cancel_latency: directly tied to BACK-03; primary VPS-or-not decision.
  - alt_yield: opportunity-cost benchmark; directly enters the ship-gate threshold.

The grid catches cliffs / plateaus / saddle points that simple ±20% perturbation
ignores. Output is a 5×5 list-of-lists; downstream plots (Plan 05-09) render it
as a heatmap.

D2 anti-pattern guard: every cell run gets a FRESH RUN_MANIFEST with
parent_run_id=parent_manifest.run_id (PROTO-01 mid-run knob-change semantics).

[[backtest-perturbation-grid-pydantic-reflection]]
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
import structlog

from ..config.schema import BotConfig
from ..manifest.schema import RunManifest
from ..manifest.writer import build_run_manifest
from .perturbation import (
    KnobLeaf,
    ReplayInputs,
    _set_leaf_by_path,
    enumerate_perturbable_leaves,
)
from .replay import ReplayEngine
from .ship_gate import evaluate_ship_gate

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ContourCell:
    """A single cell in the 2D contour grid."""

    knob_a_value: float
    knob_b_value: float
    p5_pnl: float


def _locate_value(leaves: list[KnobLeaf], path: str) -> float:
    """Find the unperturbed value for a given dotted knob path in the leaf list."""
    for lf in leaves:
        if lf.path == path:
            return float(lf.value)
    raise ValueError(f"contour_2d_knobs path {path!r} not found in BotConfig numeric leaves")


async def run_2d_contour_grid(
    base_config: BotConfig,
    replay_inputs: ReplayInputs,
    *,
    parent_manifest: RunManifest,
    grid_size: int = 5,
) -> list[list[ContourCell]]:
    """Per BACK-08: 5×5 grid on `base_config.backtest.contour_2d_knobs`.

    Default knobs: (execution.cancel_latency_budget_s, screener.alt_yield).
    No NaN cells permitted — raises RuntimeError if a child run produces NaN p5.

    Each cell run gets a FRESH RUN_MANIFEST with parent_run_id (D2 anti-pattern
    guard — PROTO-01 mid-run knob-change semantics).

    Returns a grid_size × grid_size list-of-lists indexed [a_idx][b_idx].
    """
    knob_a_path, knob_b_path = base_config.backtest.contour_2d_knobs[:2]
    pct = float(base_config.backtest.perturbation_pct)
    leaves = enumerate_perturbable_leaves(base_config)
    a_unp = _locate_value(leaves, knob_a_path)
    b_unp = _locate_value(leaves, knob_b_path)

    if a_unp == 0.0 or b_unp == 0.0:
        raise ValueError(
            f"contour_2d: knob value is zero for path "
            f"{'a' if a_unp == 0.0 else 'b'} "
            f"({'a: ' + knob_a_path if a_unp == 0.0 else 'b: ' + knob_b_path}). "
            "Relative perturbation is undefined at zero. Set a non-zero default or "
            "choose a different contour knob pair."
        )
    a_grid = np.linspace(a_unp * (1.0 - pct), a_unp * (1.0 + pct), grid_size)
    b_grid = np.linspace(b_unp * (1.0 - pct), b_unp * (1.0 + pct), grid_size)

    base_dict = base_config.model_dump(mode="json")
    grid: list[list[ContourCell]] = []
    for a_idx, a_value in enumerate(a_grid):
        row: list[ContourCell] = []
        for b_idx, b_value in enumerate(b_grid):
            perturbed = _set_leaf_by_path(base_dict, knob_a_path, float(a_value))
            perturbed = _set_leaf_by_path(perturbed, knob_b_path, float(b_value))
            perturbed_config = BotConfig.model_validate(perturbed)
            child_manifest = build_run_manifest(
                perturbed_config,
                parent_run_id=parent_manifest.run_id,
            )
            # Flat constructor — mirrors sweeps/cancel_latency.py pattern
            engine = ReplayEngine(
                config=perturbed_config,
                market_id=replay_inputs.market_id,
                side=replay_inputs.side,
                parquet_root=replay_inputs.parquet_root,
                sqlite_path=replay_inputs.sqlite_path,
                cancel_latency_s=replay_inputs.cancel_latency_s,
                voluntary_cancel_branch=replay_inputs.voluntary_cancel_branch,
                sigma_others_multiplier=replay_inputs.sigma_others_multiplier,
                run_id=child_manifest.run_id,
                manifest=child_manifest,
            )
            result = await engine.run(seed_from_config=True)
            verdict = evaluate_ship_gate(
                result.daily_pnl,
                manifest=child_manifest,
                config=perturbed_config,
            )
            if math.isnan(verdict.p5_annualized_pnl):
                raise RuntimeError(
                    f"NaN in contour cell ({a_idx}, {b_idx}) at " f"({knob_a_path}={a_value}, {knob_b_path}={b_value})"
                )
            cell = ContourCell(
                knob_a_value=float(a_value),
                knob_b_value=float(b_value),
                p5_pnl=verdict.p5_annualized_pnl,
            )
            row.append(cell)
            log.info(
                "backtest.contour_2d.cell",
                a_path=knob_a_path,
                a_value=float(a_value),
                b_path=knob_b_path,
                b_value=float(b_value),
                p5=verdict.p5_annualized_pnl,
            )
        grid.append(row)
    return grid


def contour_grid_to_parquet(
    grid: list[list[ContourCell]],
    *,
    run_id: str,
    knob_a_path: str,
    knob_b_path: str,
    parquet_root: Path = Path("data/parquet/backtest_results"),
) -> Path:
    """Serialize the grid cells to a single parquet under sweep_axis=contour_2d.

    Path layout:
        <parquet_root>/run_id=<run_id>/sweep_axis=contour_2d/<a_path>__<b_path>/results.parquet

    Path-traversal guard mirrors loss_model/artifact.py:51-62.
    """
    parquet_root_resolved = parquet_root.resolve()
    safe_pair = f"{knob_a_path}__{knob_b_path}"
    out_dir = (parquet_root / f"run_id={run_id}" / "sweep_axis=contour_2d" / safe_pair).resolve()
    if not out_dir.is_relative_to(parquet_root_resolved):
        raise ValueError(f"contour_2d path traversal blocked: {out_dir} " f"is outside {parquet_root_resolved}")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [{"a_value": c.knob_a_value, "b_value": c.knob_b_value, "p5_pnl": c.p5_pnl} for row in grid for c in row]
    out_path = out_dir / "results.parquet"
    pl.DataFrame(rows).write_parquet(out_path)
    return out_path


__all__ = ["ContourCell", "run_2d_contour_grid", "contour_grid_to_parquet"]
