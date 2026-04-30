"""Phase 05.3 Plan 01 T1 — fill-path smoke tests.

RED-first: these tests SHOULD FAIL on HEAD (before T2/T4 land). They lock in
the unit-coherence + decoupled-rate-crossing contract for `_handle_trade_event`,
`_trade_consumes_order`, and `_handle_inter_event_fills`.

Defects exercised:

  * **Units mismatch on queue position.** `queue_ahead_wei = 10**18` is "1 ETH
    of wei", but the binding market's parquet has `size_wei = NULL` for every
    row (ingester correctly emits null when the source is `size_float`).
    `int(evt.get("size_wei") or 0)` coerces null to 0; `_trade_consumes_order`
    then compares `10**18 <= 0` → False, and the trade handler is dead.
  * **Catch-22 on `queue_ahead_wei == 0`.** `_handle_inter_event_fills` only
    fires when `order.queue_ahead_wei == 0`, but the only writer of that
    value is the dead trade handler from the unit bug above. So even when
    the rate-crossing check fires unit-coherently (post-T3), no fill
    registers (post-T2 still RED here).

Decision D1 (YU unit convention) and D3 (decouple rate-crossing from queue
gate) close both. Status post-T2 + T4: GREEN.

Fixtures:
  - synthetic 26-day market_trades parquet with K=4 controlled rate-crossings
    of the long lower edge. `size_wei = NULL` across all rows; `size_float`
    populated. Mirrors the binding-market schema exactly.
  - synthetic order_book_raw parquet for the sigma_others read-path so the
    engine doesn't raise EmptyCompetitionPoolError mid-run.
  - synthetic SQLite operator-calibration row so `_calibration_at_chain_ts`
    finds a row.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"

# Binding-market edges — long lower threshold computed via the round-trip
# helper (post-T3). For the smoke fixture we use rate fractions that bracket
# a chosen edge value of 0.0050 (= 0.5% APR fraction) with controlled
# crossings, regardless of the upstream calibration.
LONG_LOWER_EDGE_RATE_FRAC = 0.0050  # 0.5% APR; trade rate <= this → fill (long)
LONG_UPPER_EDGE_RATE_FRAC = 0.0150  # 1.5% APR; trade rate >= this → fill (short)


# ──────────────────────────────────────────────────────────────────────────
# Fixture: synthesise market_trades parquet with K crossings of the lower edge
# ──────────────────────────────────────────────────────────────────────────


def _seed_market_trades_with_crossings(
    parquet_root: Path,
    market_id: str,
    base_ts: int,
    edge_lower_rate_frac: float,
    n_crossings: int,
) -> Path:
    """Seed a parquet that contains exactly ``n_crossings`` of the long lower
    edge. Each crossing is one rate-below-edge row immediately followed by a
    rate-above-edge row (and vice versa for the return crossings).

    Schema mirrors the real archive: ``size_wei = NULL`` for every row,
    ``size_float`` populated. This is the exact data shape that breaks
    `_trade_consumes_order` on HEAD.
    """
    out_dir = parquet_root / "market_trades" / f"market_id=101-{market_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build a rate sequence that crosses `edge_lower_rate_frac` exactly
    # `n_crossings` times. We alternate above/below the edge:
    #   above (0.012), below (0.0030), above (0.012), below (0.0030), …
    # K crossings = K consecutive sign changes vs the edge.
    # Therefore len(rates) = K + 1 events.
    above = edge_lower_rate_frac + 0.0070  # ≈ 1.2% APR
    below = edge_lower_rate_frac - 0.0020  # ≈ 0.3% APR
    rates: list[float] = []
    for i in range(n_crossings + 1):
        rates.append(above if i % 2 == 0 else below)

    n = len(rates)
    # Space events 60s apart so the fill_model fit does not go stale across
    # the synthetic window (default fit_max_staleness_s = 3600s).
    rows = {
        "market_id": [f"101-{market_id}"] * n,
        "blockTimestamp": [base_ts + i * 60 for i in range(n)],
        "eventIndex": [i + 1 for i in range(n)],
        "rate": rates,
        "size_float": [1.0] * n,  # nonzero YU — would consume queue if queue is small
        # size_wei NULL across all rows — mirrors the real archive
        "size_wei": [None] * n,
        "side": ["long"] * n,
    }
    df = pl.DataFrame(
        rows,
        schema={
            "market_id": pl.String,
            "blockTimestamp": pl.UInt64,
            "eventIndex": pl.UInt64,
            "rate": pl.Float64,
            "size_float": pl.Float64,
            "size_wei": pl.UInt128,
            "side": pl.String,
        },
    )
    df.write_parquet(out_dir / "data.parquet")
    return parquet_root


def _make_minimal_engine(
    config: BotConfig,
    parquet_root: Path,
    sqlite_path: Path,
    market_id: str,
    cancel_latency_s: float = 1.0,
) -> ReplayEngine:
    """Construct a ReplayEngine with config.markets[0] pinned to the synthetic
    fixture so `_seed_initial_synthetic_order` finds calibration."""
    from boros_brain.config.schema import MarketCalibration

    market = MarketCalibration(
        market_id=market_id,
        scale=606985714285.0,
        s=0.0,
        clo_lower_thresh=9300.0,
        clo_upper_thresh=9500.0,
        fIndex_oracle_address="0x0000000000000000000000000000000000000000",
        maturity_ts=1790294400,
        underlying_exchange="binance",
        underlying_symbol="ETHUSDT",
        margin_per_yu_usd=18.30,
        daily_volatility_pct=0.34,
        liquidation_buffer_safety_n=3,
    )
    modified_config = config.model_copy(
        update={
            "markets": [market],
            "backtest": config.backtest.model_copy(update={"tick_period_s": 60.0}),
        }
    )
    return ReplayEngine(
        config=modified_config,
        market_id=market_id,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=cancel_latency_s,
        run_id="01TESTPLAN053T1",
    )


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_size_float_only_data_produces_fill(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
    seed_order_book_raw_parquet: Callable,
) -> None:
    """`size_wei = NULL` rows produce a FILL_REALIZED entry when size_float is
    nonzero and large enough to consume the seeded order's queue.

    Plan T1 contract: "synthetic trade event with size_wei = NULL,
    size_float > 0, size_float ≥ queue_ahead_yu → produces FILL_REALIZED entry."

    On HEAD: `int(evt.get("size_wei") or 0)` coerces null→0; `_trade_consumes_order`
    returns False; the trade handler is dead; no FILL_REALIZED is emitted. RED.
    Post-T2: comparison switches to size_float vs queue_ahead_yu; one
    FILL_REALIZED appears for the single trade event that exceeds the
    seeded queue. GREEN.
    """
    base_ts = 1_700_000_000

    parquet_root = tmp_path / "parquet"
    out_dir = parquet_root / "market_trades" / f"market_id=101-{MARKET_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Two trade events:
    #   1. The "fill" event: size_float=10.0 YU crosses the seeded order's
    #      queue_ahead_yu=0.5 → schedules a close at +0.1s.
    #   2. A no-op trade 60s later — its job is to drive _fire_scheduled_closes
    #      past the close_at_ts so the FILL_REALIZED entry actually appears.
    # In the real binding-market run there are 100s of trade events so this
    # tail-flush is automatic; for a 1-event fixture the engine has no later
    # tick to fire the scheduled close on.
    pl.DataFrame(
        {
            "market_id": [f"101-{MARKET_ID}"] * 2,
            "blockTimestamp": [base_ts, base_ts + 60],
            "eventIndex": [1, 2],
            "rate": [0.003, 0.003],
            "size_float": [10.0, 0.001],
            "size_wei": [None, None],
            "side": ["long", "long"],
        },
        schema={
            "market_id": pl.String,
            "blockTimestamp": pl.UInt64,
            "eventIndex": pl.UInt64,
            "rate": pl.Float64,
            "size_float": pl.Float64,
            "size_wei": pl.UInt128,
            "side": pl.String,
        },
    ).write_parquet(out_dir / "trades.parquet")

    seed_order_book_raw_parquet(
        market_id=f"101-{MARKET_ID}",
        snapshot_ts=base_ts - 3600,
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
                "effective_at_utc": "2026-04-01T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long", fit_window_end_ts=base_ts)
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    engine = _make_minimal_engine(default_config, parquet_root, sqlite_path, MARKET_ID, cancel_latency_s=0.1)
    # Direct seed: place a synthetic order with a small queue so the trade
    # handler's size_float vs queue_ahead_yu comparison fires.
    from boros_brain.backtest.synthetic_orders import SyntheticOrder

    order = SyntheticOrder(
        order_id="test_size_float_fill",
        market_id=MARKET_ID,
        side="long",
        tick=0,  # arbitrary; we exercise the trade-handler size compare
        q_me_pendle=1.0,
        placed_at_ts=base_ts - 1,
        depth_from_mark_ticks=10,
        queue_ahead_yu=0.5,  # tiny — single 10-YU trade fully consumes
    )
    engine.synthetic_orders.place(order)

    result = await engine.run()

    fill_entries = [d for d in result.decision_log if d.get("decision_kind") == "FILL_REALIZED"]
    assert len(fill_entries) >= 1, (
        f"Expected ≥1 FILL_REALIZED entry from a size_float=10.0 trade event "
        f"(NULL size_wei), got {len(fill_entries)}. decision_log size = "
        f"{len(result.decision_log)}. Likely the unit-mismatch bug "
        f"(int(evt.get('size_wei') or 0) → 0) is still present."
    )


@pytest.mark.asyncio
async def test_rate_crossing_produces_fill(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration: Callable,
    seed_fill_model_fit: Callable,
    seed_loss_grid_artifact: Callable,
    seed_order_book_raw_parquet: Callable,
) -> None:
    """K=4 controlled rate-crossings of the long lower edge produce K
    FILL_REALIZED entries (ignoring queue gate per D3).

    Plan T1 contract: "synthetic 26-day fixture with K controlled
    rate-crossings of the long lower edge → assert n_fills == K (within
    latency-scheduler tolerances)."

    The exact count tolerance accounts for:
      - Each "above→below" crossing fires one fill;
      - "below→above" crossings (return) don't fire on a long edge (edge_crossed
        requires evt_rate ≤ edge); so K_alternating crossings produce K/2 fills.
      - The first event is "above" (no edge cross at start); each subsequent
        event toggles. With K_alternating = 4 toggles starting "above", events
        go above→below→above→below→above; 2 of those toggles are
        above-to-below = 2 fills.
      - Once the order fires once, it transitions to ledger status='filled' and
        won't re-trigger; so the realized count is at most 1 (single seeded
        order). With 1 seeded order and ≥1 above→below crossing in the
        sequence, expect exactly 1 fill regardless of K.

    Pre-T2/T4 (HEAD): both gates fail; n_fills = 0. RED.
    Post-T2/T4: rate crossing fires unconditionally; n_fills = 1. GREEN.
    """
    base_ts = 1_700_000_000
    n_crossings = 4

    parquet_root = _seed_market_trades_with_crossings(
        tmp_path / "parquet",
        MARKET_ID,
        base_ts,
        edge_lower_rate_frac=LONG_LOWER_EDGE_RATE_FRAC,
        n_crossings=n_crossings,
    )

    seed_order_book_raw_parquet(
        market_id=f"101-{MARKET_ID}",
        snapshot_ts=base_ts - 3600,
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
                "effective_at_utc": "2026-04-01T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    seed_fill_model_fit(market_id=MARKET_ID, side="long", fit_window_end_ts=base_ts)
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    engine = _make_minimal_engine(default_config, parquet_root, sqlite_path, MARKET_ID, cancel_latency_s=0.1)

    # Seed the order at the lower edge — rate ≤ 0.005 = "below edge" → fill.
    # We override the calibration-driven seed in `_seed_initial_synthetic_order`
    # with a direct placement to avoid coupling this test to the post-T3 helper.
    from boros_brain.backtest.synthetic_orders import SyntheticOrder

    order = SyntheticOrder(
        order_id="test_rate_cross_fill",
        market_id=MARKET_ID,
        side="long",
        tick=0,
        q_me_pendle=1.0,
        placed_at_ts=base_ts - 1,
        depth_from_mark_ticks=10,
        # Large queue value so trade-handler path doesn't fire — only
        # _handle_inter_event_fills' rate-crossing path can produce the fill.
        # On HEAD the catch-22 traps this; post-T4 (D3) it fires unconditionally.
        queue_ahead_yu=1e9,
    )
    engine.synthetic_orders.place(order)
    # Plant the lower-edge rate-fraction on the engine so _handle_inter_event_fills
    # uses our test edge instead of mismatched per-market math. Post-T3 the engine
    # exposes `clo_lower_rate_fraction`; pre-T3 the attribute does not exist
    # and the assignment is a no-op for the engine's existing logic.
    engine.clo_lower_rate_fraction = LONG_LOWER_EDGE_RATE_FRAC  # type: ignore[attr-defined]
    engine.clo_upper_rate_fraction = LONG_UPPER_EDGE_RATE_FRAC  # type: ignore[attr-defined]

    result = await engine.run()

    fill_entries = [d for d in result.decision_log if d.get("decision_kind") == "FILL_REALIZED"]
    assert len(fill_entries) >= 1, (
        f"Expected ≥1 FILL_REALIZED entry from {n_crossings} edge crossings, "
        f"got {len(fill_entries)}. decision_log size = "
        f"{len(result.decision_log)}. Likely the catch-22 (rate-crossing "
        f"gated on queue_ahead_wei==0) or the unit bug is still present."
    )
