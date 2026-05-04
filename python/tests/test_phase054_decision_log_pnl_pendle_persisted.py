"""Phase 05.4-03 Bug D — pnl_pendle column must persist in decision_log parquet.

FILL_REALIZED rows already include pnl_pendle (replay.py:1471-1483). Per-tick HOLD/CANCEL
rows (replay.py:777-792) MUST also include pnl_pendle=0.0 so polars schema inference is
stable and parquet-side aggregation matches in-memory aggregation.

Strategy: run ReplayEngine with _n_synthetic_orders + _sim_duration_s to generate
HOLD/CANCEL rows, inject a synthetic FILL_REALIZED entry, then flush to parquet and verify:
  1. pnl_pendle column exists with dtype Float64
  2. parquet sum of pnl_pendle for FILL_REALIZED rows matches in-memory sum to 1e-9 rel
  3. non-FILL rows have pnl_pendle == 0.0

[[phase-05-4-bug-d-pnl-pendle-parquet]]
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
FILL_PNL_PENDLE = -0.123456789  # synthetic fill P&L for test verification


@pytest.fixture
def backtest_config(default_config: BotConfig, tmp_path: Path) -> BotConfig:
    """default_config with output_parquet_root pointing to tmp_path."""
    return default_config.model_copy(
        update={
            "backtest": default_config.backtest.model_copy(
                update={"output_parquet_root": str(tmp_path / "backtest_results")}
            )
        }
    )


@pytest.mark.asyncio
async def test_pnl_pendle_persists_in_decision_log_parquet(
    tmp_path: Path,
    backtest_config: BotConfig,
    seed_market_trades_parquet: Callable,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
) -> None:
    """Bug D fix: pnl_pendle column exists in decision_log parquet with dtype Float64.

    RED on HEAD: pnl_pendle column missing from HOLD/CANCEL rows — polars schema
    inference either nulls it or drops it entirely when mixing row shapes.

    GREEN after fix: pnl_pendle=0.0 explicit in every HOLD/CANCEL row +
    schema_overrides at write site forces Float64 dtype for all rows.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 100.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    manifest = build_run_manifest(backtest_config)
    engine = ReplayEngine(
        config=backtest_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    # Run for 5 ticks with 1 synthetic order → 5 HOLD/CANCEL rows (no pnl_pendle on HEAD)
    result = await engine.run(_n_synthetic_orders=1, _sim_duration_s=5)

    # Inject a synthetic FILL_REALIZED entry (as the actual engine would produce)
    result.decision_log.append(
        {
            "run_id": manifest.run_id,
            "current_chain_ts": 1_700_000_010,
            "order_id": "synthetic-fill",
            "decision_kind": "FILL_REALIZED",
            "fill_ts": 1_700_000_005.0,
            "close_at_ts": 1_700_000_010.0,
            "fill_rate": 0.05,
            "close_rate": 0.051,
            "pnl_pendle": FILL_PNL_PENDLE,
        }
    )

    # Force flush to parquet (threshold=1 forces all rows)
    engine._decision_log_stream_threshold = 1
    engine._flush_decision_log_to_parquet(final=True)

    # Verify parquet file exists
    decision_log_dir = tmp_path / "backtest_results" / f"run_id={manifest.run_id}" / "decision_log"
    parquet_files = sorted(decision_log_dir.glob("*.parquet"))
    assert parquet_files, f"No decision_log parquet files found under {decision_log_dir}"

    # Test 1: pnl_pendle column exists with correct dtype
    df = pl.concat([pl.read_parquet(str(p)) for p in parquet_files])
    assert "pnl_pendle" in df.columns, f"pnl_pendle missing from decision_log parquet columns: {df.columns}"
    assert (
        df.schema["pnl_pendle"] == pl.Float64
    ), f"pnl_pendle dtype wrong: {df.schema['pnl_pendle']} (expected Float64)"


@pytest.mark.asyncio
async def test_parquet_aggregation_matches_in_memory_to_1e_9_rel(
    tmp_path: Path,
    backtest_config: BotConfig,
    seed_market_trades_parquet: Callable,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
) -> None:
    """Bug D fix: parquet pnl_pendle sum matches in-memory sum to 1e-9 relative tolerance.

    RED on HEAD: parquet sum is biased (FILL_REALIZED row may be dropped or null-typed
    due to heterogeneous schema inference when HOLD/CANCEL rows lack pnl_pendle key).

    GREEN after fix: all rows have explicit pnl_pendle float, schema_overrides force
    Float64, and the parquet sum agrees with the in-memory sum.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 100.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    manifest = build_run_manifest(backtest_config)
    engine = ReplayEngine(
        config=backtest_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    result = await engine.run(_n_synthetic_orders=1, _sim_duration_s=5)

    # Inject a FILL_REALIZED entry with known pnl
    result.decision_log.append(
        {
            "run_id": manifest.run_id,
            "current_chain_ts": 1_700_000_010,
            "order_id": "synthetic-fill",
            "decision_kind": "FILL_REALIZED",
            "fill_ts": 1_700_000_005.0,
            "close_at_ts": 1_700_000_010.0,
            "fill_rate": 0.05,
            "close_rate": 0.051,
            "pnl_pendle": FILL_PNL_PENDLE,
        }
    )

    # Flush to parquet
    engine._decision_log_stream_threshold = 1
    engine._flush_decision_log_to_parquet(final=True)

    # Compute in-memory pnl sum (FILL_REALIZED only — matches _aggregate_daily_pnl pattern)
    in_memory_pnl_sum = sum(
        float(d.get("pnl_pendle", 0.0)) for d in result.decision_log if d.get("decision_kind") == "FILL_REALIZED"
    )

    assert in_memory_pnl_sum != 0.0, "Fixture didn't produce FILL_REALIZED entries with non-zero pnl — bad test setup"

    # Compute parquet pnl sum
    decision_log_dir = tmp_path / "backtest_results" / f"run_id={manifest.run_id}" / "decision_log"
    parquet_pnl_sum = (
        pl.scan_parquet(str(decision_log_dir / "*.parquet"))
        .filter(pl.col("decision_kind") == "FILL_REALIZED")
        .select(pl.col("pnl_pendle").sum())
        .collect()
        .item()
    )

    assert math.isclose(in_memory_pnl_sum, parquet_pnl_sum, rel_tol=1e-9), (
        f"parquet aggregation drift: in_memory={in_memory_pnl_sum!r}, "
        f"parquet={parquet_pnl_sum!r} (rel diff = "
        f"{abs(in_memory_pnl_sum - parquet_pnl_sum) / max(abs(in_memory_pnl_sum), 1e-12):.2e})"
    )


@pytest.mark.asyncio
async def test_non_fill_rows_have_pnl_pendle_zero(
    tmp_path: Path,
    backtest_config: BotConfig,
    seed_market_trades_parquet: Callable,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
) -> None:
    """Bug D fix: non-FILL_REALIZED rows have pnl_pendle == 0.0 exactly.

    RED on HEAD: non-FILL rows are missing pnl_pendle entirely (null or absent).
    GREEN after fix: explicit 0.0 for all HOLD/CANCEL rows in both memory and parquet.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 100.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    manifest = build_run_manifest(backtest_config)
    engine = ReplayEngine(
        config=backtest_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    result = await engine.run(_n_synthetic_orders=1, _sim_duration_s=5)

    # Inject a FILL_REALIZED entry so the parquet has mixed row types
    result.decision_log.append(
        {
            "run_id": manifest.run_id,
            "current_chain_ts": 1_700_000_010,
            "order_id": "synthetic-fill",
            "decision_kind": "FILL_REALIZED",
            "fill_ts": 1_700_000_005.0,
            "close_at_ts": 1_700_000_010.0,
            "fill_rate": 0.05,
            "close_rate": 0.051,
            "pnl_pendle": FILL_PNL_PENDLE,
        }
    )

    engine._decision_log_stream_threshold = 1
    engine._flush_decision_log_to_parquet(final=True)

    decision_log_dir = tmp_path / "backtest_results" / f"run_id={manifest.run_id}" / "decision_log"
    df = pl.concat([pl.read_parquet(str(p)) for p in sorted(decision_log_dir.glob("*.parquet"))])

    # Filter to non-FILL rows
    non_fill_df = df.filter(pl.col("decision_kind") != "FILL_REALIZED")
    assert non_fill_df.height > 0, "No non-FILL rows found — check _n_synthetic_orders/sim_duration_s"

    # All non-FILL rows must have pnl_pendle == 0.0 exactly
    non_fill_pnl_min = non_fill_df["pnl_pendle"].min()
    non_fill_pnl_max = non_fill_df["pnl_pendle"].max()
    assert (
        non_fill_pnl_min == 0.0 and non_fill_pnl_max == 0.0
    ), f"non-FILL rows have non-zero pnl_pendle: min={non_fill_pnl_min}, max={non_fill_pnl_max}"
