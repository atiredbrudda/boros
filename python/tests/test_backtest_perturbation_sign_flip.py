"""BACK-08 — perturbation sign flip detection.

Test functions:
  - test_detect_sign_flip_unit_table: hand-rolled table covering all sign-flip cases
  - test_run_perturbation_grid_returns_one_row_per_leaf: monkeypatched ReplayEngine
  - test_fragile_knob_flagged_when_sign_flips: targeted sign flip on one knob
  - test_fragile_flag_does_not_auto_fail_ship_gate: fragile flag never raises

[[backtest-perturbation-grid-pydantic-reflection]]
[[backtest-fragility-and-sign-flip-detection]]
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from boros_brain.backtest.perturbation import (
    ReplayInputs,
    detect_sign_flip,
    enumerate_perturbable_leaves,
    run_perturbation_grid,
)
from boros_brain.backtest.schemas import ReplayOutput, ShipGateVerdict
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


# ---------------------------------------------------------------------------
# Unit table: detect_sign_flip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unp, low, high, expected",
    [
        # Same-sign pos — no flip
        (0.05, 0.03, 0.07, False),
        # Same-sign neg — no flip
        (-0.05, -0.07, -0.03, False),
        # Flip from pos to neg via low
        (0.05, -0.03, 0.07, True),
        # Flip from pos to neg via high
        (0.05, 0.03, -0.07, True),
        # Flip from neg to pos via low
        (-0.05, 0.03, -0.07, True),
        # Zero baseline with pos high: sign(0.0)=0, sign(0.05)=+1 → sign mismatch → flip
        (0.0, 0.0, 0.05, True),
        # Zero baseline with one non-zero sign: sign(0.0)=0, sign(-0.05)=-1 → flip
        (0.0, -0.05, 0.05, True),
        # Both perturbed zero with positive baseline: sign(0.05)=+1, sign(0.0)=0 → flip
        (0.05, 0.0, 0.05, True),
    ],
)
def test_detect_sign_flip_unit_table(unp: float, low: float, high: float, expected: bool) -> None:
    """BACK-08: tri-valued sign extraction; 0.0 → 0 and never spuriously flips."""
    result = detect_sign_flip(unp, low, high)
    assert result is expected, f"detect_sign_flip({unp}, {low}, {high}) = {result}, expected {expected}"


# ---------------------------------------------------------------------------
# Integration: run_perturbation_grid (monkeypatched)
# ---------------------------------------------------------------------------


def _make_replay_inputs(tmp_path: Path) -> ReplayInputs:
    return ReplayInputs(
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path / "parquet",
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=1.0,
        voluntary_cancel_branch="benign",
    )


@pytest.mark.asyncio
async def test_run_perturbation_grid_returns_one_row_per_leaf(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: run_perturbation_grid returns one PerturbationRow per leaf.

    Monkeypatches ReplayEngine.run so the test runs in < 5 s.
    """

    async def _stub_run(self: object) -> ReplayOutput:
        return ReplayOutput(
            rows=[],
            decision_log=[],
            daily_pnl=np.array([0.001] * 30, dtype=np.float64),
            n_amm_violations=0,
            event_index_coverage="full",
        )

    monkeypatch.setattr(
        "boros_brain.backtest.replay.ReplayEngine.run",
        _stub_run,
        raising=True,
    )

    parent_manifest = build_run_manifest(default_config)
    replay_inputs = _make_replay_inputs(tmp_path)

    rows = await run_perturbation_grid(
        default_config,
        replay_inputs,
        parent_manifest=parent_manifest,
    )

    expected_n = len(enumerate_perturbable_leaves(default_config))
    assert len(rows) == expected_n, f"Expected {expected_n} rows (one per perturbable leaf), got {len(rows)}"
    # Verify all 8 fields are populated on the first row
    if rows:
        r = rows[0]
        assert r.knob_path
        assert isinstance(r.baseline_p5_pnl, float)
        assert isinstance(r.low_p5_pnl, float)
        assert isinstance(r.high_p5_pnl, float)
        assert isinstance(r.low_value, float)
        assert isinstance(r.high_value, float)
        assert isinstance(r.unperturbed_value, float)
        assert isinstance(r.fragile, bool)


@pytest.mark.asyncio
async def test_fragile_knob_flagged_when_sign_flips(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: exactly one knob flagged fragile when one low-perturbation flips sign.

    Monkeypatches evaluate_ship_gate to return negative p5 ONLY for the
    screener.alt_yield low perturbation (chosen because alt_yield has a non-zero
    default so target_low_value is distinct from baseline value).
    """
    TARGET_PATH = "screener.alt_yield"
    leaves = enumerate_perturbable_leaves(default_config)
    alt_yield_leaf = next(lf for lf in leaves if lf.path == TARGET_PATH)
    target_low_value = alt_yield_leaf.value * (1.0 - default_config.backtest.perturbation_pct)
    assert alt_yield_leaf.value != 0.0, "alt_yield must be non-zero for this test to be valid"

    async def _stub_run(self: object) -> ReplayOutput:
        return ReplayOutput(
            rows=[],
            decision_log=[],
            daily_pnl=np.array([0.001] * 30, dtype=np.float64),
            n_amm_violations=0,
            event_index_coverage="full",
        )

    monkeypatch.setattr(
        "boros_brain.backtest.replay.ReplayEngine.run",
        _stub_run,
        raising=True,
    )

    def _stub_verdict(daily_pnl: object, *, manifest: object, config: BotConfig) -> ShipGateVerdict:
        # Return negative p5 only for the target knob's low perturbation
        val = config.screener.alt_yield
        p5 = -0.005 if abs(val - target_low_value) < 1e-9 else 0.005
        return ShipGateVerdict(
            p5_annualized_pnl=p5,
            threshold=0.06,
            passed=False,
            n_resamples=2000,
            block_seconds=86400,
            seed=42,
            manifest_run_id=manifest.run_id,  # type: ignore[union-attr]
        )

    monkeypatch.setattr(
        "boros_brain.backtest.perturbation.evaluate_ship_gate",
        _stub_verdict,
        raising=True,
    )

    parent_manifest = build_run_manifest(default_config)
    replay_inputs = _make_replay_inputs(tmp_path)

    rows = await run_perturbation_grid(
        default_config,
        replay_inputs,
        parent_manifest=parent_manifest,
    )

    fragile_rows = [r for r in rows if r.fragile]
    assert len(fragile_rows) == 1, (
        f"Expected exactly 1 fragile row, got {len(fragile_rows)}: " f"{[r.knob_path for r in fragile_rows]}"
    )
    assert fragile_rows[0].knob_path == TARGET_PATH


@pytest.mark.asyncio
async def test_fragile_flag_does_not_auto_fail_ship_gate(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: run_perturbation_grid returns rows normally even when fragile=True.

    Sign-flip is RECORDED, not auto-fail (RESEARCH.md L1045 — operator decides).
    """

    async def _stub_run(self: object) -> ReplayOutput:
        return ReplayOutput(
            rows=[],
            decision_log=[],
            daily_pnl=np.array([0.001] * 30, dtype=np.float64),
            n_amm_violations=0,
            event_index_coverage="full",
        )

    monkeypatch.setattr(
        "boros_brain.backtest.replay.ReplayEngine.run",
        _stub_run,
        raising=True,
    )

    # Return alternating positive/negative to guarantee at least one fragile knob
    call_count = [0]

    def _stub_verdict(daily_pnl: object, *, manifest: object, config: BotConfig) -> ShipGateVerdict:
        call_count[0] += 1
        # Every 3rd call returns negative (low perturbation of first leaf → fragile)
        p5 = -0.005 if call_count[0] % 3 == 0 else 0.005
        return ShipGateVerdict(
            p5_annualized_pnl=p5,
            threshold=0.06,
            passed=p5 > 0.06,
            n_resamples=2000,
            block_seconds=86400,
            seed=42,
            manifest_run_id=manifest.run_id,  # type: ignore[union-attr]
        )

    monkeypatch.setattr(
        "boros_brain.backtest.perturbation.evaluate_ship_gate",
        _stub_verdict,
        raising=True,
    )

    parent_manifest = build_run_manifest(default_config)
    replay_inputs = _make_replay_inputs(tmp_path)

    # Must NOT raise — fragile flag is RECORDED only
    rows = await run_perturbation_grid(
        default_config,
        replay_inputs,
        parent_manifest=parent_manifest,
    )
    assert isinstance(rows, list), "run_perturbation_grid must return a list, not raise"
    assert len(rows) > 0, "Expected at least one row"
