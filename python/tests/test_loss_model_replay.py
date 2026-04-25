"""LOSS-01 replay tests (Plan 03-01, Task 2).

Test IDs:
- T-03-R-01 (LOSS-01): per-cell aggregation across the full grid.
- T-03-R-02 (T-03-05 mitigation): no look-ahead on close trade.
- T-03-R-03 (A6): fee terms absorbed into pnl_pendle.
- T-03-R-04: skipped (Phase-5 backtest concern; placeholder).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
import structlog

from boros_brain.config.schema import BotConfig, DataConfig, MarketCalibration
from boros_brain.loss_model.fit import fit_loss_grid
from boros_brain.loss_model.replay import (
    build_per_fill_pnl_from_frame,
    replay_historical_fills,
)

FIXTURES = Path(__file__).parent / "fixtures"
MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _tiny_config() -> BotConfig:
    return BotConfig(
        mode="backtest",
        strategy_version="test",
        market_id=MARKET_ID,
        side="long",
        root_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        data=DataConfig(rpc_url_arbitrum="https://example.com"),
        markets=[
            MarketCalibration(
                market_id=MARKET_ID,
                scale=1.0,
                s=1.0,
                clo_lower_thresh=0.0,
                clo_upper_thresh=1.0,
                fIndex_oracle_address="0x0000000000000000000000000000000000000099",
                # 365 days after the fixture's anchor block_ts so tau_days > 0
                maturity_ts=1_700_000_000 + 365 * 86400,
            )
        ],
    )


def test_per_cell_aggregation_via_fit(tmp_path: Path) -> None:
    """T-03-R-01 — load synthetic per-fill fixture, drive fit_loss_grid (bypassing
    DuckDB replay), and assert grid coverage is healthy."""
    df = pl.read_parquet(FIXTURES / "loss_grid_synthetic_fills.parquet")
    config = _tiny_config()

    # Build PerFillPnL list from the fixture (fixture already carries pnl_pendle
    # and tau_days — bypass the fee-recompute path).
    fills = build_per_fill_pnl_from_frame(df, config=config, market_id=MARKET_ID)
    assert len(fills) > 0

    # Drive the fit (persist=False — no SQLite needed)
    artifact = fit_loss_grid(
        config,
        MARKET_ID,
        "long",
        window_start_ts=0,
        window_end_ts=1_700_000_000,
        run_id="test-run-fit",
        persist=False,
        fills=fills,
    )
    # Fixture covers 7 depth × 6 tau = 42 cells per side; we only want 'long'.
    assert len(artifact.cells) >= 30
    # Every present cell should have at least the fixture's edge n=5.
    for cell in artifact.cells:
        assert cell.n_samples >= 5


def test_no_look_ahead(tmp_path: Path) -> None:
    """T-03-R-02 / T-03-05 — close-event at blockTimestamp BEFORE fill is rejected.

    Construct a one-fill-no-close fixture: fill at (ts=100, eventIndex=5);
    only opposite-side trade is at (ts=99, eventIndex=99) — strictly before
    the fill. The replay frame's close_rate column is None (LEFT JOIN miss).
    Assert the fill is SKIPPED with a warning log.
    """
    config = _tiny_config()

    # Inject the post-SQL frame directly: this is what _REPLAY_SQL would emit
    # after the look-ahead constraint filters the only available close trade.
    injected = pl.DataFrame(
        {
            "market_id": [MARKET_ID],
            "side": ["long"],
            "fill_event_index": [5],
            "fill_block_ts": [100],
            "fill_rate": [0.10],
            "fill_size_str": ["1000000000000000000"],  # 1.0 in wei
            "close_rate": [None],
            "close_block_ts": [None],
            "close_event_index": [None],
        },
        schema={
            "market_id": pl.Utf8,
            "side": pl.Utf8,
            "fill_event_index": pl.Int64,
            "fill_block_ts": pl.Int64,
            "fill_rate": pl.Float64,
            "fill_size_str": pl.Utf8,
            "close_rate": pl.Float64,
            "close_block_ts": pl.Int64,
            "close_event_index": pl.Int64,
        },
    )

    with structlog.testing.capture_logs() as captured:
        out = replay_historical_fills(
            config,
            MARKET_ID,
            window_start_ts=0,
            window_end_ts=1_000_000,
            fills_frame=injected,
        )
    assert out == [], f"look-ahead filter produced ghost rows: {out}"
    events = [r["event"] for r in captured]
    assert "loss_model.replay_close_missing" in events, events


def test_fees_term_included() -> None:
    """T-03-R-03 / A6 — pnl_pendle differs from gross by AT LEAST the sum of fees."""
    from boros_brain.loss_model.config import LossModelConfig

    config = _tiny_config()
    # BotConfig.loss_model attaches in Plan 03-02; until then use the default sub-model.
    fees = LossModelConfig().fees
    # One synthetic fill: long, size=1.0, fill_rate=0.10, close_rate=0.11, tau=30 days.
    block_ts = 1_700_000_000
    injected = pl.DataFrame(
        {
            "market_id": [MARKET_ID],
            "side": ["long"],
            "fill_event_index": [1],
            "fill_block_ts": [block_ts],
            "fill_rate": [0.10],
            "fill_size_float": [1.0],
            "close_rate": [0.11],
            "close_block_ts": [block_ts + 30],
            "close_event_index": [2],
            "tau_days": [30.0],
            "depth_from_mark_ticks": [0],
        }
    )
    rows = build_per_fill_pnl_from_frame(injected, config=config, market_id=MARKET_ID)
    assert len(rows) == 1
    r = rows[0]

    # Pre-fee gross for long: size × (close - fill) × tau/365
    gross = 1.0 * (0.11 - 0.10) * (30.0 / 365.0)

    # Each fee term must be > 0 (default knobs are all positive).
    assert r.fee_taker_pendle > 0
    assert r.fee_settlement_pendle > 0
    assert r.fee_entrance_amortized_pendle > 0
    assert r.fee_gas_pendle > 0
    sum_fees = r.fee_taker_pendle + r.fee_settlement_pendle + r.fee_entrance_amortized_pendle + r.fee_gas_pendle

    # gross - sum_fees == pnl_pendle (within float tolerance)
    assert abs((gross - sum_fees) - r.pnl_pendle) < 1e-12, (
        f"fee absorption mismatch: gross={gross}, sum_fees={sum_fees}, " f"pnl={r.pnl_pendle}"
    )

    # Sanity: configured taker rate matches what was applied
    expected_taker = 1.0 * 0.10 * (30.0 / 365.0) * fees.taker_fee_rate
    assert r.fee_taker_pendle == pytest.approx(expected_taker, rel=1e-9)


def test_short_side_pnl_sign() -> None:
    """T-03-R-05 / WR-03 — short-side P&L sign: close_rate < fill_rate is profitable.

    For a short fill at fill_rate=0.12 closed at close_rate=0.10:
      gross = fill_size × (close_rate - fill_rate) × tau/365  → negative
      negated for short → positive (profit: APR moved in our favour)
      pnl_pendle = gross - fees → must remain positive for reasonable fee levels.

    This test guards the formula against accidental double-negation or sign flip.
    """
    config = _tiny_config()
    block_ts = 1_700_000_000
    # Short profitable: APR fell from 0.12 to 0.10 → close below fill = profit for short.
    injected_short = pl.DataFrame(
        {
            "market_id": [MARKET_ID],
            "side": ["short"],
            "fill_event_index": [2],
            "fill_block_ts": [block_ts],
            "fill_rate": [0.12],
            "fill_size_float": [1.0],
            "close_rate": [0.10],
            "close_block_ts": [block_ts + 30],
            "close_event_index": [3],
            "tau_days": [30.0],
            "depth_from_mark_ticks": [0],
        }
    )
    rows = build_per_fill_pnl_from_frame(injected_short, config=config, market_id=MARKET_ID)
    assert len(rows) == 1
    r = rows[0]

    # Gross before fees: -(fill_size × (close - fill) × tau/365) = -(1×(0.10-0.12)×30/365)
    gross = -(1.0 * (0.10 - 0.12) * (30.0 / 365.0))
    assert gross > 0, "pre-fee gross must be positive for a profitable short close"

    sum_fees = r.fee_taker_pendle + r.fee_settlement_pendle + r.fee_entrance_amortized_pendle + r.fee_gas_pendle
    # Net of fees must still be positive (default fee knobs are small relative to gross).
    assert r.pnl_pendle > 0, (
        f"short profitable close must yield positive pnl_pendle "
        f"(gross={gross:.6f}, fees={sum_fees:.6f}, pnl={r.pnl_pendle:.6f})"
    )
    # gross - sum_fees == pnl_pendle (within float tolerance)
    assert (
        abs((gross - sum_fees) - r.pnl_pendle) < 1e-12
    ), f"fee absorption mismatch: gross={gross}, sum_fees={sum_fees}, pnl={r.pnl_pendle}"


@pytest.mark.skip(reason="integration test requires Phase-1 parquet fixture; lands in Phase 5 backtest")
def test_amm_conservation_preserved() -> None:
    """T-03-R-04 — replay does not raise AMMConsumptionIdentityError on real Phase-1 data.

    Future-phase concern; placeholder here for traceability."""
    pass
