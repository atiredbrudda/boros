"""Phase 05.4-04 — backtest replay must pass current_chain_ts into refit_once
(Bug C end-to-end integration; Plan 03 added the parameter, Plan 04 wires the consumer).

Invariant tested: every call to fill_model.refit_loop.refit_once made by
ReplayEngine._maybe_refit_fill_model must pass current_chain_ts (not None).

Strategy: directly test _maybe_refit_fill_model which is the call site added by
Plan 04. Three tests cover:
  1. First call triggers refit with current_chain_ts == passed ts.
  2. Cadence throttling: subsequent calls within cadence window are no-ops.
  3. After cadence elapses, next call triggers a second refit.

Also verifies the run() wiring: the simulated-tick path calls _maybe_refit_fill_model.

[[phase-05-4-bug-c-look-ahead-fix]]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig

ROOT = Path(__file__).resolve().parents[2]
MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"

# Replay window anchored at a fixed epoch so tests are deterministic.
BASE_TS = 1_743_465_600  # 2026-04-01T00:00:00Z


@pytest.fixture
def shortlist_config(tmp_path: Path) -> BotConfig:
    """Load shortlist config with tmp sqlite path (no real DB needed for this test)."""
    base = load_config(ROOT / "strategy" / "v0.5-phase05.1-shortlist.yaml")
    return base.model_copy(
        update={"infra": base.infra.model_copy(update={"sqlite_path": str(tmp_path / "state.sqlite")})}
    )


@pytest.fixture
def engine(shortlist_config: BotConfig, tmp_path: Path) -> ReplayEngine:
    return ReplayEngine(
        config=shortlist_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path,
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=2.0,
        run_id="test-phase054-chain-ts-refit",
    )


@pytest.mark.asyncio
async def test_maybe_refit_fill_model_passes_current_chain_ts(
    engine: ReplayEngine,
    shortlist_config: BotConfig,
) -> None:
    """Unit test: _maybe_refit_fill_model calls refit_once with current_chain_ts keyword.

    Directly verifies the call site signature (Bug C integration point).
    """
    captured_kwargs: list[dict] = []

    async def _capture_refit(
        config: BotConfig,
        run_id: str,
        *,
        current_chain_ts: int | None = None,
    ) -> None:
        captured_kwargs.append({"current_chain_ts": current_chain_ts})

    test_ts = BASE_TS + 12345

    with patch(
        "boros_brain.fill_model.refit_loop.refit_once",
        new=_capture_refit,
    ):
        await engine._maybe_refit_fill_model(test_ts)

    assert len(captured_kwargs) == 1, "Expected exactly 1 refit_once call on first invocation"
    assert captured_kwargs[0]["current_chain_ts"] == test_ts, (
        f"current_chain_ts mismatch: got {captured_kwargs[0]['current_chain_ts']}, " f"expected {test_ts}"
    )
    assert engine._last_refit_chain_ts == test_ts, "_last_refit_chain_ts not updated after successful refit"


@pytest.mark.asyncio
async def test_maybe_refit_fill_model_cadence_throttling(
    engine: ReplayEngine,
    shortlist_config: BotConfig,
) -> None:
    """_maybe_refit_fill_model must not refit more often than refit_cadence_s."""
    call_count = 0

    async def _count_refit(config: BotConfig, run_id: str, *, current_chain_ts: int | None = None) -> None:
        nonlocal call_count
        call_count += 1

    cadence = int(shortlist_config.fill_model.refit_cadence_s)

    with patch(
        "boros_brain.fill_model.refit_loop.refit_once",
        new=_count_refit,
    ):
        # First call — must fire (engine is fresh, _last_refit_chain_ts is None).
        await engine._maybe_refit_fill_model(BASE_TS)
        # Within-cadence calls — must be no-ops.
        await engine._maybe_refit_fill_model(BASE_TS + cadence // 2)
        await engine._maybe_refit_fill_model(BASE_TS + cadence - 1)

    assert call_count == 1, (
        f"Expected 1 refit call (cadence={cadence}s); got {call_count}. "
        f"Throttling logic in _maybe_refit_fill_model is broken."
    )

    # Advance past one full cadence — must fire again.
    with patch(
        "boros_brain.fill_model.refit_loop.refit_once",
        new=_count_refit,
    ):
        await engine._maybe_refit_fill_model(BASE_TS + cadence + 1)

    assert call_count == 2, f"Expected 2nd refit after cadence elapsed; still at {call_count}"


@pytest.mark.asyncio
async def test_maybe_refit_fill_model_chain_ts_never_exceeds_current(
    engine: ReplayEngine,
    shortlist_config: BotConfig,
) -> None:
    """All refit calls must pass current_chain_ts <= the ts passed to _maybe_refit_fill_model.

    Anti-look-ahead invariant: the fit window end is bounded to the current tick.
    """
    captured_ts: list[int] = []
    cadence = int(shortlist_config.fill_model.refit_cadence_s)

    async def _capture(config: BotConfig, run_id: str, *, current_chain_ts: int | None = None) -> None:
        assert current_chain_ts is not None, "current_chain_ts must not be None in backtest mode"
        captured_ts.append(int(current_chain_ts))

    ticks = [BASE_TS, BASE_TS + cadence + 10, BASE_TS + 2 * cadence + 20]

    with patch(
        "boros_brain.fill_model.refit_loop.refit_once",
        new=_capture,
    ):
        for ts in ticks:
            await engine._maybe_refit_fill_model(ts)

    assert len(captured_ts) == len(
        ticks
    ), f"Expected {len(ticks)} refit calls (one per cadence step); got {len(captured_ts)}"

    # Each captured chain_ts must equal the ts that triggered the refit.
    for passed_ts, captured in zip(ticks, captured_ts, strict=False):
        assert captured == passed_ts, (
            f"Refit received wrong chain_ts: captured={captured}, passed={passed_ts}. "
            f"No future-data must enter the fit window."
        )


@pytest.mark.asyncio
async def test_run_sim_path_calls_maybe_refit(
    engine: ReplayEngine,
    shortlist_config: BotConfig,
) -> None:
    """The _sim_duration_s code path must invoke _maybe_refit_fill_model.

    Verifies end-to-end wiring: run() with _sim_duration_s > 0 calls the refit
    helper. Uses a mock so no real I/O is performed.

    Note: the _sim_duration_s path skips the initial-event refit block (which
    requires a real event from iter_events). The periodic refit fires from
    _maybe_emit_tick → _maybe_refit_fill_model via the run() loop. This test
    verifies _maybe_refit_fill_model is wired and called at least once.
    """
    refit_call_count = 0

    async def _mock_refit_method(chain_ts: int) -> None:
        nonlocal refit_call_count
        refit_call_count += 1

    # The sim path synthesises SIM_S ticks starting at BASE_TS.
    # We need > cadence ticks to trigger at least 1 refit.
    cadence = int(shortlist_config.fill_model.refit_cadence_s)
    sim_s = cadence + 60  # one full cadence + buffer

    with patch.object(engine, "_maybe_refit_fill_model", side_effect=_mock_refit_method):
        await engine.run(
            _n_synthetic_orders=0,  # no orders — no _build_evaluate_input calls
            _sim_duration_s=sim_s,
        )

    assert refit_call_count >= 1, (
        f"Expected _maybe_refit_fill_model to be called ≥1 time over {sim_s}s sim; "
        f"got {refit_call_count}. Check that run() wires _maybe_refit_fill_model."
    )
