"""Phase 05.2 Wave 4 — Sparse-tick synthesis integration tests.

Tests that _iter_chain_seconds is wired into the main run() loop and that
synthesised ticks produce decision_log entries, respect look-ahead invariants,
and that decision_log is streamed to parquet at 100k boundaries.

Bug #4 fix (Phase 05.2 Wave 4): _maybe_emit_tick now fires at 1 Hz on the
chain-time clock between trade events, not only on trade events themselves.

See [[backtest-1hz-tick-synthesis-2026-04-30]].
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _seed_two_event_trades(
    tmp_path: Path,
    market_id: str,
    t0: int,
    t1: int,
    rate: float = 0.009,
) -> Path:
    """Seed a market_trades parquet with exactly 2 events spaced t1-t0 seconds apart."""
    parquet_root = tmp_path / "parquet"
    out_dir = parquet_root / "market_trades" / f"market_id={market_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "market_id": [market_id, market_id],
            "blockTimestamp": [t0, t1],
            "eventIndex": [0, 0],
            "rate": [rate, rate],
            "size_wei": [0, 0],
            "side": ["buy", "buy"],
        }
    ).write_parquet(out_dir / "trades.parquet")
    return parquet_root


def _make_engine(
    config: BotConfig,
    parquet_root: Path,
    sqlite_path: Path,
    n_synthetic_orders: int = 1,
    tick_period_s: float = 1.0,
) -> ReplayEngine:
    """Build a ReplayEngine with the given parquet/sqlite roots."""
    modified_config = config.model_copy(
        update={"backtest": config.backtest.model_copy(update={"tick_period_s": tick_period_s})}
    )
    manifest = build_run_manifest(modified_config)
    engine = ReplayEngine(
        config=modified_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )
    # Pre-seed synthetic orders so decision_log accumulates entries.
    from boros_brain.backtest.synthetic_orders import SyntheticOrder

    for i in range(n_synthetic_orders):
        engine.synthetic_orders.place(
            SyntheticOrder(
                order_id=f"test_order_{i}",
                market_id=MARKET_ID,
                side="long",
                tick=9400,
                q_me_pendle=1.0,
                placed_at_ts=0,
                depth_from_mark_ticks=50,
                # Phase 05.3 D1: queue_ahead is YU-denominated (was wei).
                # 1e7 YU is enormous vs any plausible trade event size_float.
                queue_ahead_yu=1e7,
                r_accum=0.0,
                t_frac=1.0,
            )
        )
    return engine


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthetic_ticks_emitted_between_trade_events(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
    seed_order_book_raw_parquet: Callable,
) -> None:
    """With 2 real events at t=1700000000 and t=1700001000, after engine.run(),
    decision_log contains one entry per second per in-flight order across
    [t0, t1] interval. With 1 in-flight order and tick_period_s=1.0, expect
    exactly 1001 entries with current_chain_ts in [t0, t1].

    This verifies the _iter_chain_seconds integration into run() (Bug #4 fix).
    """
    t0 = 1_700_000_000
    t1 = t0 + 1000

    parquet_root = _seed_two_event_trades(tmp_path, MARKET_ID, t0, t1)

    # Seed order_book_raw so sigma_others parquet read doesn't raise.
    seed_order_book_raw_parquet(
        market_id=MARKET_ID,
        snapshot_ts=t0 - 1,
        ticks_with_sizes={9350: 50, 9400: 100, 9450: 50},
        parquet_root=parquet_root,
    )

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
        [("2026-04-25T00:00:00Z", t0 - 1, 1.0, 50.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    engine = _make_engine(
        default_config,
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        n_synthetic_orders=1,
        tick_period_s=1.0,
    )

    result = await engine.run()

    # Filter to HOLD/CANCEL ticks (not FILL_REALIZED rows)
    tick_entries = [
        d
        for d in result.decision_log
        if d.get("decision_kind") not in ("FILL_REALIZED",)
        and "current_chain_ts" in d
        and t0 <= d["current_chain_ts"] <= t1
    ]

    # With 1 synthetic order and 1001 chain_ts values (t0 to t1 inclusive),
    # we expect exactly 1001 decision entries in [t0, t1].
    assert len(tick_entries) == 1001, (
        f"Expected 1001 tick entries (1 order × 1001 ticks), got {len(tick_entries)}. "
        f"Total decision_log size: {len(result.decision_log)}. "
        "Bug #4 fix (_iter_chain_seconds wired into run()) may not be active."
    )

    # All chain_ts values in [t0, t1]
    for entry in tick_entries:
        assert t0 <= entry["current_chain_ts"] <= t1, f"chain_ts {entry['current_chain_ts']} out of range [{t0}, {t1}]"


@pytest.mark.asyncio
async def test_synthetic_ticks_no_lookahead(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
    seed_order_book_raw_parquet: Callable,
) -> None:
    """Every decision_log entry has current_chain_ts <= last_real_event_ts.

    T-05-05 look-ahead invariant: synthesised ticks must not project beyond
    the last real event. _iter_chain_seconds stops at last_ts (no extrapolation).
    """
    t0 = 1_700_000_000
    t1 = t0 + 100

    parquet_root = _seed_two_event_trades(tmp_path, MARKET_ID, t0, t1)
    seed_order_book_raw_parquet(
        market_id=MARKET_ID,
        snapshot_ts=t0 - 1,
        ticks_with_sizes={9350: 50, 9400: 100, 9450: 50},
        parquet_root=parquet_root,
    )

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
        [("2026-04-25T00:00:00Z", t0 - 1, 1.0, 50.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    engine = _make_engine(
        default_config,
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        n_synthetic_orders=1,
    )

    result = await engine.run()

    # No decision_log entry should have chain_ts > last_real_event_ts (t1)
    future_entries = [d for d in result.decision_log if "current_chain_ts" in d and d["current_chain_ts"] > t1]
    assert not future_entries, (
        f"Look-ahead detected: {len(future_entries)} entries have chain_ts > {t1}. "
        f"First offender: {future_entries[0] if future_entries else 'none'}"
    )


@pytest.mark.asyncio
async def test_synthetic_ticks_dont_double_anchor(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
    seed_order_book_raw_parquet: Callable,
) -> None:
    """_maybe_anchor_snapshot is called at most once per snapshot boundary (3600s).

    Synthesised ticks between real events must NOT trigger extra anchor calls.
    _maybe_anchor_snapshot checks the SNAPSHOT_INTERVAL_S (3600s) guard internally,
    so consecutive second-ticks within the same hour should not advance the anchor.
    """
    t0 = 1_700_000_000
    t1 = t0 + 200  # 200s gap — well within one snapshot interval

    parquet_root = _seed_two_event_trades(tmp_path, MARKET_ID, t0, t1)
    seed_order_book_raw_parquet(
        market_id=MARKET_ID,
        snapshot_ts=t0 - 1,
        ticks_with_sizes={9350: 50, 9400: 100, 9450: 50},
        parquet_root=parquet_root,
    )

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
        [("2026-04-25T00:00:00Z", t0 - 1, 1.0, 50.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    engine = _make_engine(
        default_config,
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        n_synthetic_orders=1,
    )

    anchor_call_count = 0
    original_anchor = engine._maybe_anchor_snapshot

    def _count_anchor(ts: int, evt: dict) -> None:
        nonlocal anchor_call_count
        anchor_call_count += 1
        return original_anchor(ts, evt)

    engine._maybe_anchor_snapshot = _count_anchor  # type: ignore[method-assign]

    await engine.run()

    # _maybe_anchor_snapshot is ONLY called when evt is not None (real events).
    # With 2 real events in a 200s window, it fires at most 2 times (both within
    # one 3600s snapshot interval, so _check_amm_conservation doesn't run on t1).
    assert anchor_call_count <= 2, (
        f"_maybe_anchor_snapshot called {anchor_call_count} times for 2 real events. "
        "Synthesised ticks should NOT trigger anchor calls."
    )


@pytest.mark.asyncio
async def test_decision_log_streamed_to_parquet(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration: Callable,
    seed_competition_history: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
    seed_order_book_raw_parquet: Callable,
) -> None:
    """After a run, the decision_log parquet partition exists under
    data/parquet/backtest_results/run_id=*/decision_log/ with at least one part file.

    The streaming flush is triggered at 100k entries. For this test we use a small
    override to force a flush at 10 entries (test injection) via a patched threshold.
    OR we verify that when the run produces entries, the final flush writes the parquet.

    This test uses a small fixture (few ticks) and checks the final flush path:
    after engine.run() completes, if decision_log streaming is active, a parquet
    file must exist under output_parquet_root/run_id=<X>/decision_log/.
    """
    t0 = 1_700_000_000
    t1 = t0 + 20  # 20s → 21 ticks with 1 order = 21 entries

    parquet_root = _seed_two_event_trades(tmp_path, MARKET_ID, t0, t1)
    seed_order_book_raw_parquet(
        market_id=MARKET_ID,
        snapshot_ts=t0 - 1,
        ticks_with_sizes={9350: 50, 9400: 100, 9450: 50},
        parquet_root=parquet_root,
    )

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
        [("2026-04-25T00:00:00Z", t0 - 1, 1.0, 50.0)],
        market_id=MARKET_ID,
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    # Override output_parquet_root to tmp_path
    modified_config = default_config.model_copy(
        update={
            "backtest": default_config.backtest.model_copy(
                update={"output_parquet_root": str(tmp_path / "backtest_results")}
            )
        }
    )
    manifest = build_run_manifest(modified_config)

    from boros_brain.backtest.synthetic_orders import SyntheticOrder

    engine = ReplayEngine(
        config=modified_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )
    engine.synthetic_orders.place(
        SyntheticOrder(
            order_id="test_stream_order",
            market_id=MARKET_ID,
            side="long",
            tick=9400,
            q_me_pendle=1.0,
            placed_at_ts=0,
            depth_from_mark_ticks=50,
            queue_ahead_yu=1e7,  # Phase 05.3 D1 rename; enormous YU value, no fills
            r_accum=0.0,
            t_frac=1.0,
        )
    )

    # Patch the streaming threshold to 5 so we can test flushing with a small fixture.
    engine._decision_log_stream_threshold = 5

    result = await engine.run()

    # The final flush must have written at least 1 parquet part file.
    decision_log_dir = tmp_path / "backtest_results" / f"run_id={manifest.run_id}" / "decision_log"
    parquet_files = list(decision_log_dir.glob("*.parquet")) if decision_log_dir.exists() else []

    assert parquet_files, (
        f"No decision_log parquet files found under {decision_log_dir}. "
        f"Expected streaming flush after run() completion. "
        f"decision_log has {len(result.decision_log)} in-memory entries."
    )

    # Total row count across all parquet parts should be > 0
    total_rows = sum(pl.read_parquet(str(p)).height for p in parquet_files)
    assert total_rows > 0, f"decision_log parquet files exist but are empty: {parquet_files}"
