"""Phase 05.5-02 — loss_model.refit_once write-side mirror of d954bc5.

Adjacent fix to Phase 05.4-03 commit ``d954bc5`` which closed the fill_model
write-side: the loss_model leg deferred ("If Plan 04 verdict lands FLAG, Phase
05.5 investigates loss_model look-ahead as first hypothesis"). RESEARCH
§Open Question 2 confirms the mirror pattern is right: 14-line shape from
``fill_model/refit_loop.py:35-58`` applies verbatim onto
``loss_model/refit_loop.py:35-71``.

Without this, the read-side filter on ``loss_grid_artifacts`` (Phase 05.5-01)
is sufficient for backtests, but live-mode loss-grid fits could still persist
with future ``window_end_ts`` from a future-time refit and re-poison the table.

Tests mirror ``test_phase054_fill_model_no_lookahead_fit.py:1-168``:

  - test_loss_model_refit_once_with_current_chain_ts_bounds_window_end:
    captured ``window_end_ts <= current_chain_ts``.
    RED on HEAD: TypeError because ``refit_once`` has no ``current_chain_ts`` kwarg.
    GREEN after fix: captured value matches.

  - test_loss_model_refit_once_default_none_uses_chain_time_now:
    no kwarg → ``window_end_ts == chain_time.now_cached()``.

[[loss-model-expected-loss-look-ahead-read-path]]
[[phase-05-4-bug-c-look-ahead-fix]]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig
from boros_brain.loss_model.refit_loop import refit_once

# Arbitrary epoch anchor well past any real market start (2026-04-01T00:00:00Z)
T0 = 1_743_465_600
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
async def test_loss_model_refit_once_with_current_chain_ts_bounds_window_end(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """Bug 1 write-side: with current_chain_ts=T passed to refit_once, window_end_ts <= T.

    Captures the window_end_ts argument passed to fit_loss_grid.
    Asserts window_end_ts <= current_chain_ts (no look-ahead).

    RED on HEAD: refit_once does not accept current_chain_ts kwarg → TypeError.
    GREEN after fix: window_end_ts is bounded to current_chain_ts.
    """
    current_chain_ts = T0 + 10 * 86400  # 10 days into the replay window

    captured_window_end_ts: list[int] = []

    def _fake_fit_loss_grid(
        config: BotConfig,
        market_id: str,
        side: str,
        window_start_ts: int,
        window_end_ts: int,
        run_id: str,
        *,
        sqlite_path: Path | None = None,
    ) -> MagicMock:
        captured_window_end_ts.append(window_end_ts)
        return MagicMock()

    with patch(
        "boros_brain.loss_model.refit_loop.fit_loss_grid",
        side_effect=_fake_fit_loss_grid,
    ):
        # This call MUST accept current_chain_ts keyword (fails on HEAD with TypeError)
        await refit_once(shortlist_config, run_id="test-bug1-loss", current_chain_ts=current_chain_ts)

    # At least one call to fit_loss_grid should have been captured
    # (loss_model fits both 'long' and 'short' for each market in config.markets).
    assert len(captured_window_end_ts) > 0, "fit_loss_grid was never called — check markets list in config"

    for captured_wend in captured_window_end_ts:
        assert captured_wend <= current_chain_ts, (
            f"look-ahead bias: window_end_ts={captured_wend} > "
            f"current_chain_ts={current_chain_ts} "
            f"(excess = {captured_wend - current_chain_ts}s)"
        )


@pytest.mark.asyncio
async def test_loss_model_refit_once_default_none_uses_chain_time_now(
    tmp_path: Path,
    shortlist_config: BotConfig,
) -> None:
    """Live-mode behavior preserved: without current_chain_ts, uses chain_time.now_cached().

    With current_chain_ts=None (default), the window_end_ts passed to
    fit_loss_grid must equal the value returned by chain_time.now_cached().
    """
    T_LIVE = 1_750_000_000  # sentinel returned by mocked chain_time.now_cached

    captured_window_end_ts: list[int] = []

    def _fake_fit_loss_grid(
        config: BotConfig,
        market_id: str,
        side: str,
        window_start_ts: int,
        window_end_ts: int,
        run_id: str,
        *,
        sqlite_path: Path | None = None,
    ) -> MagicMock:
        captured_window_end_ts.append(window_end_ts)
        return MagicMock()

    with (
        patch(
            "boros_brain.loss_model.refit_loop.chain_time.now_cached",
            new=AsyncMock(return_value=T_LIVE),
        ),
        patch(
            "boros_brain.loss_model.refit_loop.fit_loss_grid",
            side_effect=_fake_fit_loss_grid,
        ),
    ):
        # No current_chain_ts → must use chain_time.now_cached (live mode)
        await refit_once(shortlist_config, run_id="test-live-mode-loss")

    assert len(captured_window_end_ts) > 0, "fit_loss_grid was never called — check markets list in config"

    for captured_wend in captured_window_end_ts:
        assert captured_wend == T_LIVE, (
            f"live-mode: window_end_ts={captured_wend} != T_LIVE={T_LIVE} — "
            f"chain_time.now_cached not being used as window_end_ts"
        )
