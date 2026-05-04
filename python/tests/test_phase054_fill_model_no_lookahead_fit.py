"""Phase 05.4-03 Bug C — fill_model fit must NOT leak future data in backtest mode.

The read-side guard at fill_model/predict.py:91-106 warns when current_chain_ts < fit_window_end_ts.
This test pins the WRITE-side: with current_chain_ts=T passed to refit_once,
the window_end_ts argument passed to build_features_table is bounded to <= T.

Strategy: mock build_features_table and fit_market_side to capture the window_end_ts
argument without actual I/O. The invariant is: window_end_ts <= current_chain_ts.

[[phase-05-4-bug-c-look-ahead-fix]]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig
from boros_brain.fill_model.features import FeatureSet
from boros_brain.fill_model.refit_loop import refit_once

# Arbitrary epoch anchor well past any real market start (2026-04-01T00:00:00Z)
T0 = 1_743_465_600
# Market present in strategy/v0.5-phase05.1-shortlist.yaml (has markets list)
MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def shortlist_config(tmp_path: Path) -> BotConfig:
    """Load the shortlist config (has markets=[BINANCE-ETHUSDT-25SEP2026]) with tmp sqlite."""
    base = load_config(ROOT / "strategy" / "v0.5-phase05.1-shortlist.yaml")
    return base.model_copy(
        update={"infra": base.infra.model_copy(update={"sqlite_path": str(tmp_path / "test_state.sqlite")})}
    )


@pytest.mark.asyncio
async def test_refit_once_with_current_chain_ts_bounds_window_end(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """Bug C fix: with current_chain_ts=T passed to refit_once, window_end_ts <= T.

    Captures the window_end_ts argument passed to build_features_table.
    Asserts window_end_ts <= current_chain_ts (no look-ahead).

    RED on HEAD: refit_once does not accept current_chain_ts kwarg → TypeError.
    GREEN after fix: window_end_ts is bounded to current_chain_ts.
    """
    current_chain_ts = T0 + 10 * 86400  # 10 days into the replay window

    captured_window_end_ts: list[int] = []

    def _fake_build_features(
        config: BotConfig,
        market_id: str,
        window_start_ts: int,
        window_end_ts: int,
    ) -> FeatureSet:
        captured_window_end_ts.append(window_end_ts)
        # Return a minimal FeatureSet (path irrelevant — fit_market_side mocked too)
        return FeatureSet(path=tmp_path, row_count=0, column_names=[])

    mock_fit_artifact = MagicMock()

    with (
        patch(
            "boros_brain.fill_model.refit_loop.build_features_table",
            side_effect=_fake_build_features,
        ),
        patch(
            "boros_brain.fill_model.refit_loop.fit_market_side",
            return_value=mock_fit_artifact,
        ),
        patch(
            "boros_brain.fill_model.refit_loop.pl.read_parquet",
            return_value=MagicMock(),
        ),
    ):
        # This call MUST accept current_chain_ts keyword (fails on HEAD with TypeError)
        await refit_once(shortlist_config, run_id="test-bug-c", current_chain_ts=current_chain_ts)

    # At least one call to build_features_table should have been captured
    assert len(captured_window_end_ts) > 0, "build_features_table was never called — check markets list in config"

    for captured_wend in captured_window_end_ts:
        assert captured_wend <= current_chain_ts, (
            f"look-ahead bias: window_end_ts={captured_wend} > "
            f"current_chain_ts={current_chain_ts} "
            f"(excess = {captured_wend - current_chain_ts}s)"
        )


@pytest.mark.asyncio
async def test_refit_once_without_current_chain_ts_uses_chain_time_now(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """Live-mode behavior preserved: without current_chain_ts, uses chain_time.now_cached().

    With current_chain_ts=None (default), the window_end_ts passed to
    build_features_table must equal the value returned by chain_time.now_cached().
    """
    T_LIVE = 1_750_000_000  # sentinel returned by mocked chain_time.now_cached

    captured_window_end_ts: list[int] = []

    def _fake_build_features(
        config: BotConfig,
        market_id: str,
        window_start_ts: int,
        window_end_ts: int,
    ) -> FeatureSet:
        captured_window_end_ts.append(window_end_ts)
        return FeatureSet(path=tmp_path, row_count=0, column_names=[])

    with (
        patch(
            "boros_brain.fill_model.refit_loop.chain_time.now_cached",
            new=AsyncMock(return_value=T_LIVE),
        ),
        patch(
            "boros_brain.fill_model.refit_loop.build_features_table",
            side_effect=_fake_build_features,
        ),
        patch(
            "boros_brain.fill_model.refit_loop.fit_market_side",
            return_value=MagicMock(),
        ),
        patch(
            "boros_brain.fill_model.refit_loop.pl.read_parquet",
            return_value=MagicMock(),
        ),
    ):
        # No current_chain_ts → must use chain_time.now_cached (live mode)
        await refit_once(shortlist_config, run_id="test-live-mode")

    assert len(captured_window_end_ts) > 0, "build_features_table was never called — check markets list in config"

    for captured_wend in captured_window_end_ts:
        assert captured_wend == T_LIVE, (
            f"live-mode: window_end_ts={captured_wend} != T_LIVE={T_LIVE} — "
            f"chain_time.now_cached not being used as window_end_ts"
        )


def test_refit_once_keyword_only_current_chain_ts(
    default_config: BotConfig,
) -> None:
    """Keyword-only enforcement: current_chain_ts cannot be passed positionally.

    After the fix, the signature is: refit_once(config, run_id, *, current_chain_ts=None)
    Passing a positional 3rd arg MUST raise TypeError.

    RED on HEAD (no current_chain_ts param at all).
    GREEN after fix (keyword-only enforces via `*,` separator).
    """
    import asyncio

    # Passing T0 as a positional argument after run_id MUST fail.
    with pytest.raises(TypeError):
        asyncio.get_event_loop().run_until_complete(
            refit_once(default_config, "test-run-id", T0)  # positional — MUST fail
        )
