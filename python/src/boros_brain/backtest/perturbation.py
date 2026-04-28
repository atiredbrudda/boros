"""BACK-08: perturbation grid runner. ±perturbation_pct per-knob individually,
sign-flip detection on the bootstrapped 5th-percentile P&L.

Reflection-driven enumeration of BotConfig.model_dump(mode='json') leaves —
adding a knob to BotConfig automatically extends the grid (PROTO-04 SSoT).
NO hand-maintained list. The reflection idiom mirrors
tests/test_manifest_contains_all_knobs.py::_collect_leaf_paths verbatim.

D2 anti-pattern guard: every child run gets a FRESH RUN_MANIFEST with
parent_run_id=parent_manifest.run_id (PROTO-01 mid-run knob-change semantics).
A single manifest covering all perturbation children would be the D2 pitfall
(RESEARCH.md L485). Cancel-latency sweep (Plan 05-04) is the canonical analog.

Per BACK-08 ROADMAP scope verbatim: "±20% individual knob perturbations;
sign-flipping on any knob is a fragility flag in the ship-gate report."
Sign-flip is RECORDED, not auto-fail (RESEARCH.md L1045 — operator decides).

[[backtest-perturbation-grid-pydantic-reflection]]
[[backtest-fragility-and-sign-flip-detection]]
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog
from pydantic import ValidationError

from ..config.schema import BotConfig
from ..manifest.schema import RunManifest
from ..manifest.writer import build_run_manifest
from .replay import ReplayEngine
from .report import write_backtest_row
from .ship_gate import evaluate_ship_gate

log = structlog.get_logger(__name__)


# Per RESEARCH §Open Question #3 (line 1357): exclude BotConfig.backtest.* —
# strategy fragility is the question; backtest-method fragility (e.g.
# bootstrap_n_resamples) is a different, less critical question.
_PERTURBATION_EXCLUDE_PREFIXES: tuple[str, ...] = ("backtest.",)


@dataclass(frozen=True)
class KnobLeaf:
    """A single numeric leaf in the BotConfig knob tree."""

    path: str  # dotted, e.g. "decision.p_purge_default"
    value: float


@dataclass(frozen=True)
class PerturbationRow:
    """Result of a single ±perturbation_pct knob perturbation.

    fragile=True means the bootstrapped 5th-pct P&L sign flips under perturbation.
    Sign-flip is RECORDED, not auto-fail (RESEARCH.md L1045 — operator decides).
    """

    knob_path: str
    baseline_p5_pnl: float
    low_p5_pnl: float  # P&L 5th-pct under (knob × (1 - perturbation_pct))
    high_p5_pnl: float  # P&L 5th-pct under (knob × (1 + perturbation_pct))
    low_value: float
    high_value: float
    unperturbed_value: float
    fragile: bool


@dataclass(frozen=True)
class ReplayInputs:
    """Immutable record of replay inputs that DON'T change under perturbation.

    Exists so the perturbation runner can mutate `config` per-knob while
    keeping the rest of the ReplayConfig fields constant.
    """

    market_id: str
    side: Literal["long", "short"]
    parquet_root: Path
    sqlite_path: Path
    cancel_latency_s: float
    voluntary_cancel_branch: Literal["benign", "punitive"]
    sigma_others_multiplier: float = 1.0


def enumerate_perturbable_leaves(
    config: BotConfig,
    *,
    exclude_prefixes: tuple[str, ...] = _PERTURBATION_EXCLUDE_PREFIXES,
) -> list[KnobLeaf]:
    """Walk config.model_dump(mode='json') for all numeric leaves.

    Numeric leaves = float | int (NOT bool, NOT str, NOT None). Per BACK-06,
    booleans (e.g., voluntary_cancel_forfeits_accumulated) are handled by the
    forfeit_branch sweep, not here. Per RESEARCH §Open Question #3, leaves whose
    dotted path starts with any `exclude_prefixes` entry are skipped.

    Mirrors tests/test_manifest_contains_all_knobs.py::_collect_leaf_paths:53-76 —
    same _walk(d, path) recursion shape, dotted-path concatenation,
    type-narrowed leaf collection. Called once per invocation (NOT cached) so
    adding a knob to BotConfig mechanically extends the grid (PROTO-04 forcing
    function).
    """
    out: list[KnobLeaf] = []

    def _walk(d: object, path: list[str]) -> None:
        # Mirrors tests/test_manifest_contains_all_knobs.py::_collect_leaf_paths:53-76
        if isinstance(d, dict):
            for k, v in d.items():
                _walk(v, path + [k])
        elif isinstance(d, list):
            for i, v in enumerate(d):
                _walk(v, path + [str(i)])
        elif isinstance(d, int | float) and not isinstance(d, bool):
            dotted = ".".join(path)
            if any(dotted.startswith(p) for p in exclude_prefixes):
                return
            out.append(KnobLeaf(path=dotted, value=float(d)))

    _walk(config.model_dump(mode="json"), [])
    return out


def detect_sign_flip(unperturbed_pnl: float, low_pnl: float, high_pnl: float) -> bool:
    """RESEARCH.md L1036-1045 verbatim. Tri-valued sign extraction so 0.0 → 0
    and never spuriously flips.

    NaN inputs (skipped invalid perturbation direction) are treated as
    "no perturbation effect" — not a fragility signal.

    Returns True if the P&L sign changed under either perturbation direction.
    Sign-flip is RECORDED, not auto-fail (RESEARCH.md L1045 — operator decides).
    """
    sign_unp = (unperturbed_pnl > 0) - (unperturbed_pnl < 0)
    # NaN → treat as same sign as unperturbed (skip direction)
    sign_low = sign_unp if math.isnan(low_pnl) else (low_pnl > 0) - (low_pnl < 0)
    sign_high = sign_unp if math.isnan(high_pnl) else (high_pnl > 0) - (high_pnl < 0)
    return sign_unp != sign_low or sign_unp != sign_high


def _set_leaf_by_path(d: dict[str, object], dotted: str, value: float) -> dict[str, object]:
    """Walk dotted path through nested dicts/lists; return a NEW dict.

    Type-preserving: if the original value at the leaf is an int (and not bool),
    the new value is rounded to int. This ensures BotConfig.model_validate()
    succeeds for int fields (e.g. infra.heartbeat_timeout_misses) after ±pct
    perturbation produces a fractional float.

    Raises KeyError if the path doesn't exist (defensive — orchestration bug,
    not a runtime branch).
    """
    new = copy.deepcopy(d)
    parts = dotted.split(".")
    cursor: object = new
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]  # type: ignore[index]
    last = parts[-1]
    if isinstance(cursor, list):
        idx = int(last)
        original = cursor[idx]
        typed_value: int | float = (
            round(value) if isinstance(original, int) and not isinstance(original, bool) else value
        )
        cursor[idx] = typed_value
    else:
        original = cursor[last]  # type: ignore[index]
        typed_value = round(value) if isinstance(original, int) and not isinstance(original, bool) else value
        cursor[last] = typed_value  # type: ignore[index]
    return new


async def run_perturbation_grid(
    base_config: BotConfig,
    replay_inputs: ReplayInputs,
    *,
    parent_manifest: RunManifest,
    n_resamples: int = 2000,
    output_parquet_root: Path | None = None,
) -> list[PerturbationRow]:
    """Per BACK-08: ±perturbation_pct per-knob, ship-gate-compatible 5th-pct
    comparison, sign-flip detection.

    Each child run gets a fresh manifest with parent_run_id (D2 anti-pattern
    guard — mirrors plan 05-04 cancel-latency sweep verbatim).

    Sign-flip is RECORDED, not auto-fail (RESEARCH.md L1045 — operator decides).
    Returns a list of PerturbationRow whether fragile=True or False.
    """
    # Baseline run — use flat constructor pattern (mirrors sweeps/cancel_latency.py)
    base_engine = ReplayEngine(
        config=base_config,
        market_id=replay_inputs.market_id,
        side=replay_inputs.side,
        parquet_root=replay_inputs.parquet_root,
        sqlite_path=replay_inputs.sqlite_path,
        cancel_latency_s=replay_inputs.cancel_latency_s,
        voluntary_cancel_branch=replay_inputs.voluntary_cancel_branch,
        sigma_others_multiplier=replay_inputs.sigma_others_multiplier,
        run_id=parent_manifest.run_id,
        manifest=parent_manifest,
    )
    base_result = await base_engine.run(seed_from_config=True)
    base_verdict = evaluate_ship_gate(
        base_result.daily_pnl,
        manifest=parent_manifest,
        config=base_config,
    )
    baseline_p5 = base_verdict.p5_annualized_pnl

    rows: list[PerturbationRow] = []
    pct = float(base_config.backtest.perturbation_pct)
    leaves = enumerate_perturbable_leaves(base_config)
    log.info(
        "backtest.perturbation.start",
        n_leaves=len(leaves),
        baseline_p5=baseline_p5,
    )

    # Resolve output_parquet_root: use the passed absolute path if provided, else fall
    # back to the config value. The CLI always passes the resolved absolute path to
    # prevent CWD-relative writes under python/ when invoked with `uv run --directory python`.
    resolved_output_root = (
        output_parquet_root if output_parquet_root is not None else Path(base_config.backtest.output_parquet_root)
    )

    base_dict = base_config.model_dump(mode="json")
    for leaf in leaves:
        low_value = leaf.value * (1.0 - pct)
        high_value = leaf.value * (1.0 + pct)

        low_p5 = await _run_one_perturbation(
            base_dict=base_dict,
            replay_inputs=replay_inputs,
            parent_manifest=parent_manifest,
            knob_path=leaf.path,
            new_value=low_value,
            sign="low",
            output_parquet_root=resolved_output_root,
        )
        high_p5 = await _run_one_perturbation(
            base_dict=base_dict,
            replay_inputs=replay_inputs,
            parent_manifest=parent_manifest,
            knob_path=leaf.path,
            new_value=high_value,
            sign="high",
            output_parquet_root=resolved_output_root,
        )

        row = PerturbationRow(
            knob_path=leaf.path,
            baseline_p5_pnl=baseline_p5,
            low_p5_pnl=low_p5,
            high_p5_pnl=high_p5,
            low_value=low_value,
            high_value=high_value,
            unperturbed_value=leaf.value,
            fragile=detect_sign_flip(baseline_p5, low_p5, high_p5),
        )
        rows.append(row)
        log.info(
            "backtest.perturbation.row",
            knob_path=leaf.path,
            baseline_p5=baseline_p5,
            low_p5=low_p5,
            high_p5=high_p5,
            fragile=row.fragile,
        )
    return rows


async def _run_one_perturbation(
    *,
    base_dict: dict[str, object],
    replay_inputs: ReplayInputs,
    parent_manifest: RunManifest,
    knob_path: str,
    new_value: float,
    sign: Literal["low", "high"],
    output_parquet_root: Path | None = None,
) -> float:
    """Run ONE perturbation child run. Returns the ship-gate 5th-pct P&L.

    D2 anti-pattern guard: each child run gets a FRESH RUN_MANIFEST with
    parent_run_id=parent_manifest.run_id (mirrors plan 05-04 cancel-latency sweep).

    Persists a BacktestRunOutput row through write_backtest_row (Plan 05-05).
    """
    perturbed_dict = _set_leaf_by_path(base_dict, knob_path, new_value)
    try:
        perturbed_config = BotConfig.model_validate(perturbed_dict)
    except ValidationError as exc:
        # Perturbed value violates a Pydantic constraint (e.g. le=1.0 on a ratio knob).
        # Skip this direction — return NaN so the caller treats it as "no perturbation effect".
        log.warning(
            "backtest.perturbation.skip_invalid",
            knob_path=knob_path,
            new_value=new_value,
            sign=sign,
            reason=str(exc),
        )
        return math.nan
    child_manifest = build_run_manifest(
        perturbed_config,
        parent_run_id=parent_manifest.run_id,
    )
    # Flat constructor — mirrors sweeps/cancel_latency.py (replay_config alone
    # doesn't satisfy the required flat kwargs in ReplayEngine.__init__)
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
    # Persist ALL perturbed rows to parquet (sweep_axis="perturbation")
    # Use the caller-supplied absolute path to avoid CWD-relative writes under python/
    # when invoked via `uv run --directory python` (Rule 1 bug fix).
    parquet_root = (
        output_parquet_root if output_parquet_root is not None else Path(perturbed_config.backtest.output_parquet_root)
    )
    for result_row in result.rows:
        tagged = result_row.model_copy(
            update={
                "sweep_axis": "perturbation",
                "sweep_value": f"{knob_path}={sign}",
                "parent_run_id": parent_manifest.run_id,
            }
        )
        write_backtest_row(tagged, parquet_root=parquet_root)
    return verdict.p5_annualized_pnl


__all__ = [
    "KnobLeaf",
    "PerturbationRow",
    "ReplayInputs",
    "_set_leaf_by_path",
    "_PERTURBATION_EXCLUDE_PREFIXES",
    "enumerate_perturbable_leaves",
    "detect_sign_flip",
    "run_perturbation_grid",
]
