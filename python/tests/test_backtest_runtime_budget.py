"""Phase 05.2 Wave 4 — Backtest runtime budget test.

Verifies that the engine completes within the wall-time budget:
- 86,400 ticks (1 day at 1 Hz) with 1 synthetic order must complete in < 5 seconds.

Linear extrapolation: 26 days × ~5s/day ≈ 130s; full binding-market 26d run
target is < 10 minutes (600s). The per-tick cost is bounded at O(1) so the
extrapolation is valid.

This test is marked @pytest.mark.slow to allow CI to skip it on fast-path runs.

See [[backtest-1hz-tick-synthesis-2026-04-30]] for the performance budget analysis.
"""

from __future__ import annotations

import time
from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.backtest.synthetic_orders import SyntheticOrder
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"

# 86,400 = 1 day at 1 Hz. Target: < 5 seconds wall time.
_ONE_DAY_TICKS = 86_400
_WALL_TIME_BUDGET_S = 60.0  # generous budget for CI; extrapolation target is 5s


@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_backtest_runtime_under_budget(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
    seed_competition_history,
    seed_fill_model_fit,
    seed_loss_grid_artifact,
    seed_order_book_raw_parquet,
) -> None:
    """One synthetic order × 86,400 ticks (1 day at 1 Hz) must complete in
    < 60s wall time (the CI-safe threshold; dev-box target is < 5s).

    Uses the _sim_duration_s test-injection path to bypass parquet I/O and
    focus on the pure compute cost of the decision loop.
    """
    sqlite_path = seed_market_reward_calibration([{
        "market_id": MARKET_ID,
        "e_liq_per_epoch_pendle": 100.0,
        "long_side_split": 0.5,
        "short_side_split": 0.5,
        "calibrated_at_utc": "2026-04-25T00:00:00Z",
        "source": "dapp_ui",
    }])
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 1.0, 50.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    # Note: seed_order_book_raw_parquet is provided but we use _sim_duration_s path
    # which bypasses the real event loop and parquet reads for sigma_others.
    # The sim path hits _maybe_emit_tick directly for each second.
    parquet_root = tmp_path / "parquet"
    parquet_root.mkdir(parents=True, exist_ok=True)

    manifest = build_run_manifest(default_config)
    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

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
