"""Phase 05.5 Bug 2 — fill multi-close per-tick guard (TDD RED→GREEN).

Bug 2 mechanism (per RESEARCH §Bug 2):
  When one Arbitrum block contains N trade events that all individually satisfy
  ``evt_size_yu >= queue_ahead_yu`` (which becomes 0.0 after the first event of
  the block flips the order's queue to zero), ``_handle_trade_event`` schedules
  N separate ``ScheduledClose`` entries for the *same* fill. Empirically observed
  in run_id ``01KQTMW2VE7HF408T4V6XV5TDW`` PID 18460: 11 closes scheduled for
  one real fill, inflating fill_loss ~11×.

Fix: a per-tick guard set ``_pending_close_order_ids: set[str]`` lives on
``ReplayEngine``. ``_handle_trade_event`` and ``_detect_inter_event_fills``
both consult and update the set. The set clears when ``current_ts`` differs
from ``_last_handle_trade_chain_ts`` — i.e., on tick-boundary advance. Per
RESEARCH §Pitfall 5, the clearing site MUST be ``_handle_trade_event`` itself
(NOT ``_maybe_emit_tick``) because ``_maybe_emit_tick`` runs BEFORE
``_handle_trade_event`` per the ``run()`` loop in replay.py:386-402.

Tests:
  1. test_same_block_multi_event_one_close — 11 events at the same chain_ts
     produce exactly 1 ScheduledClose (not 11).
  2. test_tick_boundary_clears_guard — 1 event per tick across 2 ticks
     produces 2 ScheduledCloses (the guard clears at tick boundary).
  3. test_inter_event_respects_guard — ``_detect_inter_event_fills`` skips
     orders already scheduled by ``_handle_trade_event`` this tick.

[[fill-multi-close-per-tick-guard-2026-05-06]]
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.backtest.synthetic_orders import SyntheticOrder
from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig

ROOT = Path(__file__).resolve().parents[2]
MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"


@pytest.fixture
def shortlist_config(tmp_path: Path) -> BotConfig:
    """Load shortlist config (has markets=[BINANCE-ETHUSDT-25SEP2026])."""
    base = load_config(ROOT / "strategy" / "v0.5-phase05.1-shortlist.yaml")
    return base.model_copy(
        update={"infra": base.infra.model_copy(update={"sqlite_path": str(tmp_path / "test_state.sqlite")})}
    )


def _make_engine(config: BotConfig, tmp_path: Path) -> ReplayEngine:
    """Construct a minimal ReplayEngine for direct method invocation.

    No real I/O — we only call _handle_trade_event / _detect_inter_event_fills
    directly. The engine is constructed with parquet_root and sqlite_path that
    are never read (because we don't call .run()).
    """
    return ReplayEngine(
        config=config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path / "parquet",
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=1.0,
        run_id="01TESTPHASE055BUG2",
    )


def _place_order(
    engine: ReplayEngine,
    order_id: str,
    placed_at_ts: int,
    queue_ahead_yu: float = 0.0,
) -> None:
    """Place a synthetic in-flight order on the engine's ledger.

    queue_ahead_yu=0.0 (the default) is the pessimal case for Bug 2: every
    nonzero ``evt_size_yu`` satisfies ``0.0 <= evt_size_yu``, so without the
    guard, every event in the block schedules a close.
    """
    order = SyntheticOrder(
        order_id=order_id,
        market_id=MARKET_ID,
        side="long",
        tick=0,
        q_me_pendle=1.0,
        placed_at_ts=placed_at_ts,
        depth_from_mark_ticks=10,
        queue_ahead_yu=queue_ahead_yu,
    )
    engine.synthetic_orders.place(order)


def test_same_block_multi_event_one_close(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """11 trade events with identical blockTimestamp on a single fillable order
    produce exactly 1 ScheduledClose, not 11.

    Pre-fix (HEAD): each event satisfies ``order.queue_ahead_yu (0.0) <=
    evt_size_yu``, so ``_trade_consumes_order`` returns True every time and
    ``_handle_trade_event`` schedules N closes for one fill. RED.

    Post-fix: the per-tick guard set ``_pending_close_order_ids`` skips orders
    that have already been scheduled this tick. GREEN.
    """
    engine = _make_engine(shortlist_config, tmp_path)
    chain_ts = 1_700_000_000

    _place_order(engine, "order_multi_close", placed_at_ts=chain_ts - 1)

    # 11 events at the same chain_ts (same Arbitrum block), eventIndex 0..10.
    # All have nonzero size_float so each satisfies the queue-zero condition.
    for ei in range(11):
        evt = {
            "blockTimestamp": chain_ts,
            "eventIndex": ei,
            "rate": 0.005,  # arbitrary nonzero rate
            "size_float": 1.0,
            "size_wei": None,
            "side": "long",
        }
        engine._handle_trade_event(evt, chain_ts)

    assert len(engine._scheduled_closes) == 1, (
        f"Expected exactly 1 ScheduledClose from 11 same-block events on a "
        f"single fillable order, got {len(engine._scheduled_closes)}. "
        f"Bug 2 (fill multi-close): one fill should produce one close."
    )


def test_tick_boundary_clears_guard(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """A fill at chain_ts=T followed by a separate fill at chain_ts=T+1 produces
    2 ScheduledCloses — the per-tick guard clears at the tick boundary.

    Pre-fix (HEAD): may schedule ≥2 by accident (and indeed pin the
    natural pre-fix shape). The TEST PINS the post-fix contract: independent
    fills on different ticks each produce their own scheduled close.

    Post-fix: ``_pending_close_order_ids`` is cleared when ``current_ts``
    differs from ``_last_handle_trade_chain_ts``, so the second tick's fill
    is not skipped.
    """
    engine = _make_engine(shortlist_config, tmp_path)
    chain_ts_1 = 1_700_000_000
    chain_ts_2 = chain_ts_1 + 1  # next tick (1s apart)

    _place_order(engine, "order_tick_boundary", placed_at_ts=chain_ts_1 - 1)

    # Tick 1 — schedules 1 close.
    evt_1 = {
        "blockTimestamp": chain_ts_1,
        "eventIndex": 0,
        "rate": 0.005,
        "size_float": 1.0,
        "size_wei": None,
        "side": "long",
    }
    engine._handle_trade_event(evt_1, chain_ts_1)

    # Tick 2 — guard set should have cleared on tick-boundary advance.
    # Order is still 'active' (we haven't fired the scheduled close), and
    # queue_ahead_yu is 0.0 (set after the first schedule), so the trade
    # handler will consider it again on the new tick.
    evt_2 = {
        "blockTimestamp": chain_ts_2,
        "eventIndex": 0,
        "rate": 0.005,
        "size_float": 1.0,
        "size_wei": None,
        "side": "long",
    }
    engine._handle_trade_event(evt_2, chain_ts_2)

    assert len(engine._scheduled_closes) == 2, (
        f"Expected 2 ScheduledCloses from independent fills on 2 different "
        f"ticks (T and T+1), got {len(engine._scheduled_closes)}. The per-tick "
        f"guard must clear at tick-boundary advance, otherwise legitimate "
        f"cross-tick fills are dropped."
    )


def test_inter_event_respects_guard(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """``_detect_inter_event_fills`` respects the same per-tick guard set.

    Pre-fix (HEAD): if ``_handle_trade_event`` schedules a close, then
    ``_detect_inter_event_fills`` runs on the same trade event and order, the
    rate-crossing fallback path can also schedule a close, double-firing.
    RED (depends on rate-crossing config; pinning the desired shape).

    Post-fix: ``_detect_inter_event_fills`` consults
    ``_pending_close_order_ids`` and skips orders already scheduled by
    ``_handle_trade_event`` this tick. GREEN.
    """
    engine = _make_engine(shortlist_config, tmp_path)
    chain_ts = 1_700_000_000

    _place_order(engine, "order_inter_event", placed_at_ts=chain_ts - 1)

    # Plant the rate-fraction edges on the engine so _detect_inter_event_fills
    # uses our test edge instead of trying to resolve from the binding-market
    # calibration. Rate ≤ 0.005 = below the long lower edge → fill.
    engine.clo_lower_rate_fraction = 0.005  # type: ignore[attr-defined]
    engine.clo_upper_rate_fraction = 0.015  # type: ignore[attr-defined]

    # Event satisfies BOTH paths:
    #   * trade-handler: queue_ahead_yu (0.0) <= size_float (1.0) → schedule
    #   * inter-event:   rate (0.003) <= clo_lower (0.005) → would schedule
    evt = {
        "blockTimestamp": chain_ts,
        "eventIndex": 0,
        "rate": 0.003,  # below long lower edge
        "size_float": 1.0,
        "size_wei": None,
        "side": "long",
    }

    # Drive the same call order as the run() loop (replay.py:386-402):
    #   _detect_inter_event_fills runs FIRST, then _handle_trade_event.
    # We do _handle_trade_event first here to populate the guard set, then
    # call _detect_inter_event_fills to verify the fallback respects it.
    engine._handle_trade_event(evt, chain_ts)
    engine._detect_inter_event_fills(evt, chain_ts)

    assert len(engine._scheduled_closes) == 1, (
        f"Expected exactly 1 ScheduledClose when both _handle_trade_event "
        f"and _detect_inter_event_fills see the same fill on the same tick, "
        f"got {len(engine._scheduled_closes)}. The inter-event fallback must "
        f"consult _pending_close_order_ids to avoid double-firing."
    )
