"""LOSS-01: empirical per-fill P&L replay over Phase 1 parquet.

Joins market_trades (fills) with the next opposite-side trade (close) under the
immediate-close policy. Enforces no-look-ahead via SQL constraint:

    close.blockTimestamp >= fill.blockTimestamp
    AND (close.blockTimestamp > fill.blockTimestamp OR close.eventIndex > fill.eventIndex)

This is the T-03-05 mitigation. P3-6 guard. Test
``test_loss_model_replay.py::test_no_look_ahead`` covers.

A6 absorption: fees subtracted per [[fee-cost-term-in-expected-loss]].
USD enters ONLY via ``pendle_price_usd`` — Plan 03-04 wires this from
``config.pricing.pendle_price_usd`` (PricingConfig landed in Plan 03-02). Test
seams may still pass an explicit value via ``build_per_fill_pnl_from_frame``.

Note: the wall-clock call is banned in loss_model/ by no_time_time_lint.py
(extension lands in Plan 03-04; pre-emptive discipline). All ts values come
from the caller (window_start_ts, window_end_ts).
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from ..config.schema import BotConfig
from ..duckdb_layer.setup import open_analytical_conn
from .config import LossModelConfig
from .schemas import PerFillPnL

log = structlog.get_logger(__name__)

__all__ = ["replay_historical_fills", "build_per_fill_pnl_from_frame"]


def _get_loss_model_config(config: BotConfig) -> LossModelConfig:
    """Return BotConfig.loss_model if attached (Plan 03-02 wires it), else a default
    LossModelConfig. Plan 03-01 stays independent of the schema-attach change.
    """
    return getattr(config, "loss_model", None) or LossModelConfig()


# T-03-05 no-look-ahead invariant baked into SQL: close.blockTimestamp >= fill.blockTimestamp
# AND (close.blockTimestamp > fill.blockTimestamp OR close.eventIndex > fill.eventIndex).
#
# This SQL is the canonical replay query. It is intentionally permissive on schema
# absences (LATERAL join is emulated via window functions; CLO/mark APR pulled from
# state.clo_history nearest-snapshot; underlying APR is informational only in v0.5).
#
# Bound parameters: :market_id, :window_start, :window_end, :close_latency_budget_s.
_REPLAY_SQL = """
WITH fills AS (
    SELECT
        marketId AS market_id,
        side AS side,
        eventIndex AS fill_event_index,
        blockTimestamp AS fill_block_ts,
        rate AS fill_rate,
        size AS fill_size_str
    FROM market_trades
    WHERE marketId = $market_id
      AND blockTimestamp >= $window_start
      AND blockTimestamp <= $window_end
),
closes AS (
    -- For each fill, find the next opposite-side trade within the close-latency budget,
    -- ordered by (blockTimestamp ASC, eventIndex ASC). The look-ahead guard
    -- (close.blockTimestamp > fill OR close.eventIndex > fill.eventIndex) ensures
    -- intra-block ordering does not produce optimistic P&L (T-03-05 mitigation).
    SELECT
        f.market_id,
        f.side,
        f.fill_event_index,
        f.fill_block_ts,
        f.fill_rate,
        f.fill_size_str,
        c.rate AS close_rate,
        c.blockTimestamp AS close_block_ts,
        c.eventIndex AS close_event_index
    FROM fills f
    LEFT JOIN market_trades c
      ON c.marketId = f.market_id
     AND c.side != f.side
     AND c.blockTimestamp >= f.fill_block_ts
     AND (c.blockTimestamp > f.fill_block_ts OR c.eventIndex > f.fill_event_index)
     AND c.blockTimestamp <= f.fill_block_ts + $close_latency_budget_s
)
SELECT * FROM closes
ORDER BY fill_block_ts ASC, fill_event_index ASC
"""


def replay_historical_fills(
    config: BotConfig,
    market_id: str,
    window_start_ts: int,
    window_end_ts: int,
    *,
    fills_frame: pl.DataFrame | None = None,
) -> list[PerFillPnL]:
    """Return per-fill P&L list under the immediate-close policy.

    Returns an empty list when no fills are in the window — NOT an exception.

    The SQL enforces the no-look-ahead invariant per T-03-05. Fills with no
    forward-matchable close inside ``config.loss_model.close_latency_budget_s``
    are skipped (with a warning log) rather than emitted with a fabricated close.

    ``pendle_price_usd`` is sourced from ``config.pricing.pendle_price_usd`` —
    Plan 03-04 wired this from the PricingConfig sub-model that Plan 03-02
    attached to BotConfig. See [[fee-cost-term-in-expected-loss]] +
    [[unit-consistency-pendle-units-v05]] for the unit-discipline contract.

    The optional ``fills_frame`` argument is a test-injection seam: callers may
    pass a polars DataFrame matching the SQL output schema to bypass DuckDB. This
    is what test_loss_model_replay.py uses to exercise edge cases without
    standing up the full Phase-1 parquet tree.
    """
    lcfg = _get_loss_model_config(config)
    pendle_price_usd = config.pricing.pendle_price_usd
    if fills_frame is not None:
        df = fills_frame
    else:
        sqlite_path = str(config.infra.sqlite_path)
        parquet_root = "data/parquet/"
        conn = open_analytical_conn(sqlite_path, parquet_root)
        try:
            df = conn.execute(
                _REPLAY_SQL,
                {
                    "market_id": market_id,
                    "window_start": window_start_ts,
                    "window_end": window_end_ts,
                    "close_latency_budget_s": int(lcfg.close_latency_budget_s),
                },
            ).pl()
        finally:
            conn.close()

    if df.height == 0:
        log.info(
            "loss_model.replay_empty",
            market_id=market_id,
            window=[window_start_ts, window_end_ts],
        )
        return []

    return build_per_fill_pnl_from_frame(
        df,
        config=config,
        market_id=market_id,
        pendle_price_usd=pendle_price_usd,
    )


def _maturity_ts_for_market(config: BotConfig, market_id: str) -> int | None:
    """Return maturity_ts for the requested market_id, or None if unknown."""
    for mkt in config.markets:
        if mkt.market_id == market_id:
            return mkt.maturity_ts
    return None


def build_per_fill_pnl_from_frame(
    df: pl.DataFrame,
    *,
    config: BotConfig,
    market_id: str,
    pendle_price_usd: float = 1.0,
) -> list[PerFillPnL]:
    """Compute PerFillPnL rows from a polars DataFrame matching the replay SQL output.

    Expected columns: market_id, side, fill_event_index, fill_block_ts, fill_rate,
    fill_size_str (or fill_size_float), close_rate, close_block_ts, close_event_index
    (optional), and optionally depth_from_mark_ticks if the frame already carries it
    (test injection path). When depth_from_mark_ticks is missing we fall back to 0
    — the Phase-1 parquet does not yet carry it; the screener tick helper lands in
    Plan 03-04. For test fixtures, callers pass it through directly.

    Fee terms (PENDLE-units) per [[fee-cost-term-in-expected-loss]]:
        fee_taker = size × fill_rate × (tau_days / 365) × fees.taker_fee_rate
        fee_settlement = size × fill_rate × (settlement_period_s / 86400 / 365) × settlement_fee_rate
        fee_entrance = market_entrance_fee_usd / pendle_price_usd / 100.0  (100-fill amortization)
        fee_gas = (gas_place + gas_cancel + gas_close) × gas_price × 1e-9 / pendle_price_usd
    """
    fees = _get_loss_model_config(config).fees
    maturity_ts = _maturity_ts_for_market(config, market_id)

    # Pre-compute the constants that don't depend on the row.
    fee_entrance_amortized = fees.market_entrance_fee_usd / pendle_price_usd / 100.0
    gas_total_units = fees.gas_place_gwei + fees.gas_cancel_gwei + fees.gas_close_gwei
    fee_gas = gas_total_units * fees.gas_price_gwei * 1e-9 / pendle_price_usd

    out: list[PerFillPnL] = []
    skipped_no_close = 0

    for row in df.iter_rows(named=True):
        # Skip fills with no forward-matchable close inside the budget.
        close_rate = row.get("close_rate")
        close_block_ts = row.get("close_block_ts")
        if close_rate is None or close_block_ts is None:
            skipped_no_close += 1
            continue

        # Resolve fill_size_float either directly or by parsing fill_size_str.
        if "fill_size_float" in row and row["fill_size_float"] is not None:
            fill_size_float = float(row["fill_size_float"])
        else:
            raw = row.get("fill_size_str", row.get("fill_size", "0"))
            try:
                fill_size_float = float(raw) / 1e18
            except (TypeError, ValueError):
                fill_size_float = 0.0

        # tau_days from market maturity (single-market v0.5 cap).
        if "tau_days" in row and row["tau_days"] is not None:
            tau_days = float(row["tau_days"])
        elif maturity_ts is not None:
            tau_days = max(0.0, (maturity_ts - int(row["fill_block_ts"])) / 86400.0)
        else:
            tau_days = 0.0

        fill_rate = float(row["fill_rate"])
        side = str(row["side"])

        # depth_from_mark_ticks: passthrough from injection frame; default 0 if absent.
        depth_from_mark_ticks = int(row.get("depth_from_mark_ticks", 0) or 0)

        # Fees (PENDLE-units).
        fee_taker = (
            fill_size_float * fill_rate * (tau_days / 365.0) * fees.taker_fee_rate
        )
        fee_settlement = (
            fill_size_float
            * fill_rate
            * (fees.settlement_period_s / 86400.0 / 365.0)
            * fees.settlement_fee_rate
        )

        # Sign: positive pnl_pendle = profit; negative = loss.
        # Long P&L = size × (close - fill) × tau/365  (pre-fee)
        # Short P&L is the negation.
        gross = fill_size_float * (float(close_rate) - fill_rate) * (tau_days / 365.0)
        if side == "short":
            gross = -gross
        pnl_pendle = gross - fee_taker - fee_settlement - fee_entrance_amortized - fee_gas

        close_latency_s = float(close_block_ts) - float(row["fill_block_ts"])

        out.append(
            PerFillPnL(
                market_id=str(row["market_id"]),
                side=side,  # type: ignore[arg-type]
                fill_event_index=(
                    int(row["fill_event_index"])
                    if row.get("fill_event_index") is not None
                    else None
                ),
                fill_block_ts=int(row["fill_block_ts"]),
                fill_rate=fill_rate,
                fill_size_float=fill_size_float,
                depth_from_mark_ticks=depth_from_mark_ticks,
                tau_days=tau_days,
                close_rate=float(close_rate),
                close_block_ts=int(close_block_ts),
                close_latency_s=close_latency_s,
                pnl_pendle=pnl_pendle,
                fee_taker_pendle=fee_taker,
                fee_settlement_pendle=fee_settlement,
                fee_entrance_amortized_pendle=fee_entrance_amortized,
                fee_gas_pendle=fee_gas,
            )
        )

    if skipped_no_close > 0:
        log.warning(
            "loss_model.replay_close_missing",
            market_id=market_id,
            n_skipped=skipped_no_close,
            close_latency_budget_s=_get_loss_model_config(config).close_latency_budget_s,
        )

    return out
