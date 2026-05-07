"""Phase 05.5-01 Bug 1 fill_model leg — predict() must NOT read future-dated artifacts.

The chain-ts filter at the SQL layer (`get_latest_fit ... AND fit_window_end_ts <= ?`)
makes the predict-layer look-ahead bug structurally impossible from a correct backtest:
no future-dated row can be returned when `current_chain_ts` is supplied.

Phase-4 contract amendment (Option A): the post-filter `fit_age_s < 0` branch is now
unreachable from a correct backtest. Surfacing it via `RuntimeError` (instead of the
silent `fit_age_s = 0.0` coerce in HEAD) catches real clock-rollback or
stored-artifact corruption — both of which SHOULD halt the brain.

Mirrors the d954bc5 (Phase 05.4-03 Bug C write-side) test shape.

[[fill-model-predict-look-ahead-read-path]]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from boros_brain.config.schema import BotConfig, DataConfig
from boros_brain.fill_model.predict import (
    FillModelNoFreshFitError,
    PredictInput,
    predict,
)
from boros_brain.fill_model.schemas import FitArtifact
from boros_brain.state.writers.fill_model_fits import get_latest_fit, insert_fit_artifact

# Anchor T well past any real market start (2026-04-01T00:00:00Z + slack).
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


def _seed_fit(sqlite_path: Path, fit_window_end_ts: int) -> None:
    """Seed one FitArtifact for (MARKET_ID, SIDE) with the given fit_window_end_ts.

    Whitelist matches default config so predict() doesn't trip on missing covariates.
    """
    cfg = _tiny_config()
    artifact = FitArtifact(
        run_id=f"seed-{fit_window_end_ts}",
        fit_window_start_ts=fit_window_end_ts - 14 * 86400,
        fit_window_end_ts=fit_window_end_ts,
        market_id=MARKET_ID,
        side=SIDE,
        covariate_whitelist=list(cfg.fill_model.covariate_whitelist),
        beta=[-1.0] + [0.1] * len(cfg.fill_model.covariate_whitelist),
        beta_stderr=[0.1] * (1 + len(cfg.fill_model.covariate_whitelist)),
        log_likelihood=-100.0,
        deviance=200.0,
        aic=220.0,
        n_observations=2000,
        converged=True,
        fit_status="ok",
        event_index_coverage="full",
        created_at=fit_window_end_ts,
    )
    insert_fit_artifact(sqlite_path, artifact)


# ---------------------------------------------------------------------------
# Test 1 — get_latest_fit filters future-dated artifacts (SQL layer)
# ---------------------------------------------------------------------------


def test_get_latest_fit_filters_future_dated(tmp_path: Path) -> None:
    """RED on HEAD (TypeError: no current_chain_ts kwarg).
    GREEN after fix: returns the older artifact (T-100), not the future one (T+100).
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fit(db, fit_window_end_ts=T - 100)
    _seed_fit(db, fit_window_end_ts=T + 100)

    # WITHOUT chain-ts filter: returns absolute latest (T+100) — proves both rows are seeded.
    latest_unbounded = get_latest_fit(db, MARKET_ID, SIDE)
    assert latest_unbounded is not None
    assert (
        latest_unbounded.fit_window_end_ts == T + 100
    ), "fixture sanity: both rows must be in DB; absolute latest should be T+100"

    # WITH chain-ts filter: must return the older one (T-100), filtering the future-dated row.
    latest_bounded = get_latest_fit(db, MARKET_ID, SIDE, current_chain_ts=T)
    assert latest_bounded is not None, "T-100 row exists; SQL filter must not over-filter"
    assert latest_bounded.fit_window_end_ts == T - 100, (
        f"look-ahead bias at read layer: got fit_window_end_ts={latest_bounded.fit_window_end_ts}, "
        f"expected T-100={T - 100} (the future-dated T+100 row should be filtered out)"
    )


# ---------------------------------------------------------------------------
# Test 2 — default None preserves live-brain behavior byte-identically
# ---------------------------------------------------------------------------


def test_default_none_preserves_live_behavior(tmp_path: Path) -> None:
    """Live-brain regression guard. Calling get_latest_fit with NO kwarg (sites #5/#6
    operator paths) must return the absolute-latest row, byte-identical to HEAD.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fit(db, fit_window_end_ts=T - 100)
    _seed_fit(db, fit_window_end_ts=T + 100)

    latest = get_latest_fit(db, MARKET_ID, SIDE)
    assert latest is not None
    assert latest.fit_window_end_ts == T + 100, (
        "live-mode default-None must return absolute-latest (T+100) for byte-identical "
        "behavior with HEAD; sites #5 (cli.py:142) and #6 (report.py:40) depend on this"
    )


# ---------------------------------------------------------------------------
# Test 3 — predict() raises on negative fit_age_s post-filter (Phase-4 amendment)
# ---------------------------------------------------------------------------


def test_predict_raises_on_clock_skew(tmp_path: Path) -> None:
    """Two-branch test:

    Branch A: only future-dated row exists, chain-ts filter returns None →
              FillModelNoFreshFitError (existing contract, unchanged).

    Branch B: bypass the SQL filter (mock get_latest_fit) to force a future-dated
              return → predict raises RuntimeError (Phase-4 amendment Option A).
              Replaces the silent `fit_age_s = 0.0` coerce in HEAD.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fit(db, fit_window_end_ts=T + 100)  # only future-dated row

    cfg = _tiny_config()
    feats = {name: 0.0 for name in cfg.fill_model.covariate_whitelist}
    req = PredictInput(
        market_id=MARKET_ID,
        side=SIDE,
        depth_from_mark_ticks=5,
        queue_ahead_wei=10**18,
        current_features=feats,
        time_to_epoch_end_s=3600.0,
        current_chain_ts=T,
    )

    # Branch A: SQL filter returns no row → FillModelNoFreshFitError (existing contract).
    with pytest.raises(FillModelNoFreshFitError):
        predict(req, sqlite_path=db, config=cfg)

    # Branch B: bypass SQL filter via mock → predict() must raise RuntimeError on
    # the post-filter negative-age branch (Phase-4 contract amendment).
    fake_future_fit = FitArtifact(
        run_id="bypass-clock-skew",
        fit_window_start_ts=T + 100 - 14 * 86400,
        fit_window_end_ts=T + 100,
        market_id=MARKET_ID,
        side=SIDE,
        covariate_whitelist=list(cfg.fill_model.covariate_whitelist),
        beta=[-1.0] + [0.1] * len(cfg.fill_model.covariate_whitelist),
        beta_stderr=[0.1] * (1 + len(cfg.fill_model.covariate_whitelist)),
        log_likelihood=-100.0,
        deviance=200.0,
        aic=220.0,
        n_observations=2000,
        converged=True,
        fit_status="ok",
        event_index_coverage="full",
        created_at=T + 100,
    )

    with (
        patch(
            "boros_brain.fill_model.predict.get_latest_fit",
            return_value=fake_future_fit,
        ),
        pytest.raises(RuntimeError) as excinfo,
    ):
        predict(req, sqlite_path=db, config=cfg)

    msg = str(excinfo.value).lower()
    assert (
        "negative" in msg or "clock skew" in msg
    ), f"RuntimeError message must indicate negative age or clock skew; got: {excinfo.value!s}"


# ---------------------------------------------------------------------------
# Test 4 — replay smoke: no predict_future_dated_fit warnings emitted
# ---------------------------------------------------------------------------


def test_no_future_dated_warning_in_replay(tmp_path: Path) -> None:
    """Smoke: when a backtest-style call passes current_chain_ts=T against a DB
    that contains ONLY a T-100 row (the past), predict() must succeed and emit
    NO `predict_future_dated_fit` event. The warning was the empirical signal
    of the bug — 266,740 events on a single side in killed run 01KQYNPPE2CB46414WKHEGCZP5.
    """
    import structlog
    from structlog.testing import capture_logs

    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fit(db, fit_window_end_ts=T - 100)

    cfg = _tiny_config()
    feats = {name: 0.0 for name in cfg.fill_model.covariate_whitelist}

    # Configure structlog to use the testing capture pipeline.
    structlog.reset_defaults()

    with capture_logs() as logs:
        for tick_offset in range(5):
            req = PredictInput(
                market_id=MARKET_ID,
                side=SIDE,
                depth_from_mark_ticks=5,
                queue_ahead_wei=10**18,
                current_features=feats,
                time_to_epoch_end_s=3600.0,
                current_chain_ts=T + tick_offset,
            )
            out = predict(req, sqlite_path=db, config=cfg)
            assert 0.0 <= out.p_fill_this_epoch <= 1.0
            assert out.fit_age_s >= 0.0, f"fit_age_s must be non-negative after chain-ts filter; got {out.fit_age_s}"

    future_warnings = [log for log in logs if log.get("event") == "fill_model.predict_future_dated_fit"]
    assert len(future_warnings) == 0, f"unexpected predict_future_dated_fit events in replay: {future_warnings}"
