"""Phase 05.2 Wave 4 — Backtest runtime budget test.

Verifies that the engine completes within the wall-time budget:
- 86,400 ticks (1 day at 1 Hz) with 1 synthetic order must complete in < 30 seconds.

Linear extrapolation: 26 days × ~30s/day budget ≈ 780s; with evaluate_decision
mocked out (pure loop overhead), the actual per-tick cost is dict-lookup + append.
The 30s CI budget is intentionally generous to account for slow CI machines;
the dev-box target is < 5s.

This test is marked @pytest.mark.slow to allow CI to skip it on fast-path runs.

Uses unittest.mock.patch to replace evaluate_decision with a minimal async stub
that returns a valid EvaluateOutput without any I/O. This isolates the
_iter_chain_seconds + _maybe_emit_tick loop overhead from SQLite read overhead.

See [[backtest-1hz-tick-synthesis-2026-04-30]] for the performance budget analysis.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.decision.schemas import EvaluateOutput
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"

# 86,400 = 1 day at 1 Hz. CI-safe budget: 30s. Dev-box target: < 5s.
_ONE_DAY_TICKS = 86_400
_WALL_TIME_BUDGET_S = 30.0


def _make_stub_evaluate_output() -> EvaluateOutput:
    """Minimal valid EvaluateOutput for mocking evaluate_decision()."""
    return EvaluateOutput(
        decision_kind="HOLD",
        ev_hold_pendle=1.0,
        p_fill=0.001,
        e_loss_pendle=0.01,
        r_share_per_epoch_pendle=1.0,
        p_no_fill_and_unpurged=0.999,
        p_purge=0.0,
        cancel_cost_pendle=0.0,
        fit_status_fill="ok",
        fit_status_loss="ok",
        voluntary_cancel_branch="benign",
        reasoning={},
    )


@pytest.mark.slow
@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_backtest_runtime_under_budget(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """One synthetic order × 86,400 ticks (1 day at 1 Hz) must complete in
    < 30s wall time (CI-safe; dev-box target is < 5s).

    Uses the _sim_duration_s test-injection path and mocks out evaluate_decision
    to isolate pure loop overhead (_iter_chain_seconds + _maybe_emit_tick + append).

    This measures the overhead of the synthesised-tick iteration, not the I/O.
    The combined I/O + compute budget for a real 26d run is < 10 min (see CONTEXT.md).
    """
    parquet_root = tmp_path / "parquet"
    parquet_root.mkdir(parents=True, exist_ok=True)

    manifest = build_run_manifest(default_config)
    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=Path("/nonexistent/state.sqlite"),
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    stub_output = _make_stub_evaluate_output()

    with patch(
        "boros_brain.backtest.replay.evaluate_decision",
        new_callable=AsyncMock,
        return_value=stub_output,
    ):
        t_start = time.monotonic()
        result = await engine.run(
            _n_synthetic_orders=1,
            _sim_duration_s=_ONE_DAY_TICKS,
        )
        elapsed = time.monotonic() - t_start

    assert elapsed < _WALL_TIME_BUDGET_S, (
        f"Runtime budget exceeded: {elapsed:.1f}s > {_WALL_TIME_BUDGET_S}s "
        f"for 1 order × {_ONE_DAY_TICKS} ticks. "
        f"Linear extrapolation: 26 days would take {elapsed * 26:.0f}s (target < 600s)."
    )

    # Verify the run produced decision_log entries (not a vacuous test).
    assert len(result.decision_log) == _ONE_DAY_TICKS, (
        f"Expected {_ONE_DAY_TICKS} decision_log entries (1 order × {_ONE_DAY_TICKS} ticks), "
        f"got {len(result.decision_log)}."
    )
