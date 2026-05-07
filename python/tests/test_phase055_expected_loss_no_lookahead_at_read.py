"""Phase 05.5-01 Bug 1 loss_model leg — expected_loss() must NOT read future-dated grids.

Mirrors test_phase055_predict_no_lookahead_at_read.py shape for the loss_model leg:

- get_latest_loss_grid gains a keyword-only current_chain_ts: int | None = None
  (None = unbounded; int = SQL adds AND window_end_ts <= ?).
- expected_loss() plumbs req.current_chain_ts and raises RuntimeError on the
  post-filter negative-age branch (Phase-4 contract amendment Option A — see
  [[loss-model-expected-loss-look-ahead-read-path]]).
- _get_any_latest_loss_grid (private breaker fallback in
  decision/breakers/loss_fit_degraded.py:137-176) ALSO accepts the kwarg —
  RESEARCH §Pitfall 3 calls this out as the easy-to-miss read site #4.

[[loss-model-expected-loss-look-ahead-read-path]]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from boros_brain.config.schema import BotConfig, DataConfig
from boros_brain.decision.breakers.loss_fit_degraded import _get_any_latest_loss_grid
from boros_brain.loss_model.expected_loss import expected_loss
from boros_brain.loss_model.schemas import (
    ExpectedLossInput,
    LossGridArtifact,
    LossGridCell,
)
from boros_brain.state.writers.loss_grid_artifacts import (
    get_latest_loss_grid,
    insert_loss_grid_artifact,
)

T = 1_743_465_600
MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"
SIDE = "long"


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def _tiny_config() -> BotConfig:
    return BotConfig(
        mode="backtest",
        strategy_version="test-phase055",
        market_id=MARKET_ID,
        side=SIDE,
        root_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        data=DataConfig(rpc_url_arbitrum="https://example.com"),
    )


def _make_artifact(window_end_ts: int, *, market_id: str = MARKET_ID) -> LossGridArtifact:
    """Minimal valid LossGridArtifact at the given window_end_ts."""
    return LossGridArtifact(
        run_id=f"seed-{window_end_ts}",
        market_id=market_id,
        side=SIDE,
        window_start_ts=window_end_ts - 90 * 86400,
        window_end_ts=window_end_ts,
        fit_status="ok",
        depth_bucket_edges=[0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0],
        tau_bucket_edges_days=[0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0],
        cells=[
            LossGridCell(
                depth_bucket_idx=0,
                tau_bucket_idx=0,
                n_samples=10,
                mean_pendle=-0.01,
                std_pendle=0.005,
                p5_pendle=-0.018,
                p50_pendle=-0.01,
                p95_pendle=-0.002,
            ),
        ],
        event_index_coverage="full",
        created_at=window_end_ts,
    )


# ---------------------------------------------------------------------------
# Test 1 — get_latest_loss_grid filters future-dated artifacts (SQL layer)
# ---------------------------------------------------------------------------


def test_get_latest_loss_grid_filters_future_dated(tmp_path: Path) -> None:
    """RED on HEAD (TypeError: no current_chain_ts kwarg).
    GREEN after fix: returns the older artifact (T-100), not the future one (T+100).
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    insert_loss_grid_artifact(db, _make_artifact(T - 100))
    insert_loss_grid_artifact(db, _make_artifact(T + 100))

    # Without filter: absolute latest (fixture sanity).
    latest_unbounded = get_latest_loss_grid(db, MARKET_ID, SIDE)
    assert latest_unbounded is not None
    assert latest_unbounded.window_end_ts == T + 100

    # With filter: older row only.
    latest_bounded = get_latest_loss_grid(db, MARKET_ID, SIDE, current_chain_ts=T)
    assert latest_bounded is not None
    assert latest_bounded.window_end_ts == T - 100, (
        f"look-ahead bias at read layer: got window_end_ts={latest_bounded.window_end_ts}, " f"expected T-100={T - 100}"
    )


# ---------------------------------------------------------------------------
# Test 2 — expected_loss() raises on negative grid_age_s post-filter
# ---------------------------------------------------------------------------


def test_expected_loss_raises_on_clock_skew(tmp_path: Path) -> None:
    """Bypass the SQL filter via mock to force a future-dated grid into expected_loss.
    The post-filter grid_age_s < 0 branch must raise RuntimeError (Phase-4 amendment).

    RED on HEAD: HEAD silently coerces grid_age_s = 0.0 (no raise).
    GREEN after fix: RuntimeError with 'negative' or 'clock skew' in message.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    cfg = _tiny_config()

    fake_future_grid = _make_artifact(T + 100)

    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side=SIDE,
        depth_from_mark_ticks=0,
        time_to_maturity_s=30 * 86400,
        current_chain_ts=T,
    )

    with (
        patch(
            "boros_brain.loss_model.expected_loss.get_latest_loss_grid",
            return_value=fake_future_grid,
        ),
        pytest.raises(RuntimeError) as excinfo,
    ):
        expected_loss(req, sqlite_path=db, config=cfg)

    msg = str(excinfo.value).lower()
    assert (
        "negative" in msg or "clock skew" in msg
    ), f"RuntimeError message must indicate negative age or clock skew; got: {excinfo.value!s}"


# ---------------------------------------------------------------------------
# Test 3 — breaker private fallback _get_any_latest_loss_grid filters future-dated
# ---------------------------------------------------------------------------


def test_breaker_private_helper_filters(tmp_path: Path) -> None:
    """RESEARCH §Pitfall 3 — the easy-to-miss read site #4. Even though the
    private helper bypasses market_id, it MUST also accept current_chain_ts to
    keep the chain-ts upper bound applied.

    RED on HEAD (TypeError: no current_chain_ts kwarg).
    GREEN after fix: returns the older row.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    # Use ANY market_id for this side — the helper bypasses market filter.
    insert_loss_grid_artifact(db, _make_artifact(T - 100, market_id="ANY-MARKET-A"))
    insert_loss_grid_artifact(db, _make_artifact(T + 100, market_id="ANY-MARKET-B"))

    # Without filter: returns absolute latest (fixture sanity).
    latest_unbounded = _get_any_latest_loss_grid(db, SIDE)
    assert latest_unbounded is not None
    assert latest_unbounded.window_end_ts == T + 100

    # With filter: must return the older row.
    latest_bounded = _get_any_latest_loss_grid(db, SIDE, current_chain_ts=T)
    assert latest_bounded is not None
    assert latest_bounded.window_end_ts == T - 100, (
        f"breaker private fallback look-ahead at read: got window_end_ts={latest_bounded.window_end_ts}, "
        f"expected T-100={T - 100}"
    )
