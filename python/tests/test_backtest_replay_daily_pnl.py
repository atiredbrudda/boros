"""Regression: ReplayEngine.run() must populate ReplayOutput.daily_pnl.

Before the fix, _finalize_output left daily_pnl as the np.empty(0) default,
so any caller passing base_result.daily_pnl into block_bootstrap_pnl tripped
the "daily_pnl is empty; cannot bootstrap" guard. The perturbation grid
(perturbation.py:208) was the first such caller in the CLI sweep order.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from boros_brain.backtest.bootstrap import block_bootstrap_pnl, make_rng
from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_replay_run_populates_daily_pnl_no_fills(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """Real ReplayEngine.run() emits a non-empty daily_pnl array even with zero fills.

    block_bootstrap_pnl(daily_pnl, ...) must not raise on the result — that's
    the regression the perturbation grid was hitting in production.
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

    result = await engine.run()

    assert isinstance(result.daily_pnl, np.ndarray)
    assert result.daily_pnl.size >= 1, "daily_pnl must be non-empty for bootstrap"
    # block_bootstrap_pnl is the load-bearing downstream caller — it MUST NOT raise.
    sampled = block_bootstrap_pnl(result.daily_pnl, rng=make_rng(manifest), n_resamples=64)
    assert sampled.shape == (64,)


@pytest.mark.asyncio
async def test_replay_run_bins_realized_fill_pnl_by_day(
    default_config: BotConfig,
) -> None:
    """FILL_REALIZED entries land in the correct UTC-day bin of daily_pnl.

    Per the unit contract introduced 2026-04-30 ([[ship-gate-units-bug-2026-04-30]]),
    daily_pnl is in *daily fraction of USD collateral*, so PENDLE inputs are scaled
    by `pendle_price_usd / collateral_usd` before binning.

    Skips the parquet/sqlite seeding by using the test-injection sim path
    (`_sim_duration_s=0` + manual decision_log writes + _finalize_output).
    """
    manifest = build_run_manifest(default_config)
    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=Path("/nonexistent"),
        sqlite_path=Path("/nonexistent"),
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    # Two fills spaced ~3 days apart in the same run window.
    base_ts = 1_700_000_000
    engine.output.decision_log.extend(
        [
            {"current_chain_ts": base_ts, "decision_kind": "TICK"},
            {"current_chain_ts": base_ts + 1, "decision_kind": "FILL_REALIZED", "pnl_pendle": -0.50},
            {"current_chain_ts": base_ts + 3 * 86400, "decision_kind": "FILL_REALIZED", "pnl_pendle": -0.25},
        ]
    )

    daily = engine._aggregate_daily_pnl()

    pendle_to_usd_fraction = default_config.pricing.pendle_price_usd / default_config.sizer.collateral_usd
    assert daily.shape == (4,), f"expected 4 day bins, got {daily.shape}"
    assert daily[0] == pytest.approx(-0.50 * pendle_to_usd_fraction)
    assert daily[1] == 0.0
    assert daily[2] == 0.0
    assert daily[3] == pytest.approx(-0.25 * pendle_to_usd_fraction)


def test_aggregate_daily_pnl_empty_decision_log_returns_single_zero_day(
    default_config: BotConfig,
) -> None:
    """Empty decision_log → single zero day. Bootstrap must not raise on this."""
    manifest = build_run_manifest(default_config)
    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=Path("/nonexistent"),
        sqlite_path=Path("/nonexistent"),
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    daily = engine._aggregate_daily_pnl()

    assert daily.shape == (1,)
    assert daily[0] == 0.0
    sampled = block_bootstrap_pnl(daily, rng=make_rng(manifest), n_resamples=16)
    assert sampled.shape == (16,)


def test_aggregate_daily_pnl_includes_reward_accrual_when_no_fills(
    default_config: BotConfig,
) -> None:
    """Reward-only decision_log produces strictly positive daily_pnl.

    Verifies the load-bearing invariant: a strategy that earns via resting-order
    rewards (no fills) must produce daily_pnl > 0, NOT ≤ 0. Without this fix,
    Wave 4's ship-gate issued a false-negative FAIL.

    Per the unit contract ([[ship-gate-units-bug-2026-04-30]]), daily_pnl is the
    daily fraction of USD collateral, so the per-day expectation is the PENDLE
    accrual times `pendle_price_usd / collateral_usd`.

    Uses 60 HOLD entries per day across 3 UTC days, each with
    r_share_per_epoch_pendle = 1.0 (1 PENDLE/epoch).
    Expected per-day reward (PENDLE) ≈ 60 * 1.0 / (7 * 86400);
    expected per-day reward (USD-fraction) = above × pendle_price_usd / collateral_usd.
    """
    manifest = build_run_manifest(default_config)
    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=Path("/nonexistent"),
        sqlite_path=Path("/nonexistent"),
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    base_ts = 1_700_000_000  # arbitrary; UTC day anchor
    r_share = 1.0  # 1 PENDLE per epoch per order
    entries_per_day = 60
    n_days = 3

    for d in range(n_days):
        day_base = base_ts + d * 86400
        for s in range(entries_per_day):
            engine.output.decision_log.append(
                {
                    "current_chain_ts": day_base + s,
                    "decision_kind": "HOLD",
                    "r_share_per_epoch_pendle": r_share,
                }
            )

    daily = engine._aggregate_daily_pnl()

    # Epoch defaults: epoch_days=7.0, decision_loop_interval_s=1.0
    seconds_per_epoch = default_config.reward_share_model.epoch_days * 86400.0
    dt_per_tick = default_config.decision.decision_loop_interval_s
    pendle_to_usd_fraction = default_config.pricing.pendle_price_usd / default_config.sizer.collateral_usd
    expected_per_day = entries_per_day * r_share * (dt_per_tick / seconds_per_epoch) * pendle_to_usd_fraction

    assert daily.shape == (n_days,), f"expected {n_days} day bins, got {daily.shape}"
    for d in range(n_days):
        assert daily[d] > 0.0, f"daily[{d}] must be strictly positive for reward-only strategy"
        assert daily[d] == pytest.approx(
            expected_per_day, abs=1e-12
        ), f"daily[{d}]={daily[d]!r} != expected {expected_per_day!r}"


def test_aggregate_daily_pnl_full_epoch_integration_matches_r_share(
    default_config: BotConfig,
) -> None:
    """Integrating r_share_per_epoch_pendle over one full epoch reproduces r_share
    in USD-fraction units (the new contract — see [[ship-gate-units-bug-2026-04-30]]).

    Uses a tiny synthetic epoch (epoch_days = 1/86400 → seconds_per_epoch = 1s) so
    a single decision-log entry with dt_per_tick=1s represents one full epoch.
    Unit-conversion invariant: alive-time of exactly one epoch must yield
        sum(daily_pnl) == r_share_per_epoch_pendle × pendle_price_usd / collateral_usd
    within 1e-6 relative tolerance.
    """
    manifest = build_run_manifest(default_config)

    # Mutate config to a micro-epoch: 1/86400 days → seconds_per_epoch = 1.0s.
    # With dt_per_tick=1.0s, one entry = one full epoch → sum should equal r_share.
    tiny_epoch_config = default_config.model_copy(
        update={
            "reward_share_model": default_config.reward_share_model.model_copy(update={"epoch_days": 1.0 / 86400.0})
        }
    )

    engine = ReplayEngine(
        config=tiny_epoch_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=Path("/nonexistent"),
        sqlite_path=Path("/nonexistent"),
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    r_share = 5.0  # 5 PENDLE per epoch
    base_ts = 1_700_000_000

    # seconds_per_epoch = (1/86400) * 86400 = 1.0s; dt_per_tick = 1.0s.
    # One entry = one full epoch → reward_per_tick = 5.0 * (1.0 / 1.0) = 5.0 PENDLE.
    # In USD-fraction: 5.0 × pendle_price_usd / collateral_usd.
    engine.output.decision_log.append(
        {
            "current_chain_ts": base_ts,
            "decision_kind": "HOLD",
            "r_share_per_epoch_pendle": r_share,
        }
    )

    daily = engine._aggregate_daily_pnl()

    pendle_to_usd_fraction = tiny_epoch_config.pricing.pendle_price_usd / tiny_epoch_config.sizer.collateral_usd
    expected_usd_fraction = r_share * pendle_to_usd_fraction
    # CONTEXT.md success criterion #4: 0.01% relative tolerance for full-epoch
    # integration. With 1 Hz synthesis and exact arithmetic, this should be well
    # within tolerance. Tightened from 1e-6 (overly strict for floating-point
    # arithmetic) to 1e-4 (0.01% — the Wave 4 acceptance criterion).
    # [[backtest-1hz-tick-synthesis-2026-04-30]]
    assert daily.sum() == pytest.approx(expected_usd_fraction, rel=1e-4), (
        f"Full-epoch integration: daily.sum()={daily.sum()!r} != "
        f"expected USD-fraction {expected_usd_fraction!r} (r_share={r_share}, "
        f"pendle_to_usd_fraction={pendle_to_usd_fraction}). "
        f"Tolerance: 0.01% relative (CONTEXT.md criterion #4 / W4 acceptance)."
    )
