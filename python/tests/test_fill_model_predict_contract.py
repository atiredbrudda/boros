"""FILL-05 predict contract tests (Plan 02-03).

Test IDs: T-02-P-01 through T-02-P-04.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from boros_brain.config.schema import BotConfig, DataConfig
from boros_brain.fill_model.predict import (
    FillModelNoFreshFitError,
    FillModelStaleFeatureError,
    PredictInput,
    predict,
)
from boros_brain.fill_model.schemas import FitArtifact
from boros_brain.state.writers.fill_model_fits import insert_fit_artifact

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
    )


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def _seed_fit(sqlite_path: Path, fit_window_end_ts: int = 1_700_000_000) -> None:
    _apply_migrations(sqlite_path)
    artifact = FitArtifact(
        run_id="seed-001",
        fit_window_start_ts=fit_window_end_ts - 14 * 86400,
        fit_window_end_ts=fit_window_end_ts,
        market_id=MARKET_ID,
        side="long",
        covariate_whitelist=["basis_spread", "imbalance", "sin_settlement", "cos_settlement", "ewma_vol"],
        beta=[-1.0, 0.5, -0.3, 0.1, 0.1, 0.2],  # intercept + 5 features
        beta_stderr=[0.1, 0.05, 0.05, 0.05, 0.05, 0.05],
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


def _default_features() -> dict[str, float]:
    return {
        "basis_spread": 0.01,
        "imbalance": 0.0,
        "sin_settlement": 0.0,
        "cos_settlement": 1.0,
        "ewma_vol": 0.05,
    }


def test_predict_in_unit_interval(tmp_path: Path) -> None:
    """T-02-P-01 — happy path: p in [0, 1]."""
    db = tmp_path / "state.sqlite"
    _seed_fit(db)
    cfg = _tiny_config()
    req = PredictInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=5,
        queue_ahead_wei=10**18,
        current_features=_default_features(),
        time_to_epoch_end_s=3600.0,
        current_chain_ts=1_700_000_100,
    )
    out = predict(req, sqlite_path=db, config=cfg)
    assert 0.0 <= out.p_fill_this_epoch <= 1.0
    assert out.lambda_per_second > 0.0
    assert out.fit_run_id == "seed-001"


def test_predict_raises_on_nan(tmp_path: Path) -> None:
    """T-02-P-02 — NaN covariate → FillModelStaleFeatureError, NEVER silent fallback."""
    db = tmp_path / "state.sqlite"
    _seed_fit(db)
    cfg = _tiny_config()
    feats = _default_features()
    feats["basis_spread"] = float("nan")
    req = PredictInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=5,
        queue_ahead_wei=10**18,
        current_features=feats,
        time_to_epoch_end_s=3600.0,
        current_chain_ts=1_700_000_100,
    )
    with pytest.raises(FillModelStaleFeatureError) as excinfo:
        predict(req, sqlite_path=db, config=cfg)
    assert "basis_spread" in excinfo.value.missing_features


def test_predict_raises_on_no_fresh_fit(tmp_path: Path) -> None:
    """No row in fill_model_fits → FillModelNoFreshFitError."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    cfg = _tiny_config()
    req = PredictInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=5,
        queue_ahead_wei=10**18,
        current_features=_default_features(),
        time_to_epoch_end_s=3600.0,
        current_chain_ts=1_700_000_100,
    )
    with pytest.raises(FillModelNoFreshFitError):
        predict(req, sqlite_path=db, config=cfg)


def test_predict_raises_on_stale_fit(tmp_path: Path) -> None:
    """Fit age > fit_max_staleness_s → FillModelNoFreshFitError."""
    db = tmp_path / "state.sqlite"
    _seed_fit(db, fit_window_end_ts=1_000_000_000)  # very old
    cfg = _tiny_config()
    req = PredictInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=5,
        queue_ahead_wei=10**18,
        current_features=_default_features(),
        time_to_epoch_end_s=3600.0,
        current_chain_ts=1_700_000_000,  # ~700 million seconds newer → way past max_staleness
    )
    with pytest.raises(FillModelNoFreshFitError, match="stale"):
        predict(req, sqlite_path=db, config=cfg)


@given(
    depth_a=st.integers(min_value=0, max_value=100),
    depth_b=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_predict_monotone_in_depth(tmp_path: Path, depth_a: int, depth_b: int) -> None:
    """T-02-P-03 — increasing depth → non-increasing p."""
    db = tmp_path / "state.sqlite"
    _seed_fit(db)
    cfg = _tiny_config()
    feats = _default_features()
    base = dict(
        market_id=MARKET_ID,
        side="long",
        queue_ahead_wei=10**18,
        current_features=feats,
        time_to_epoch_end_s=3600.0,
        current_chain_ts=1_700_000_100,
    )
    p_a = predict(PredictInput(depth_from_mark_ticks=depth_a, **base), sqlite_path=db, config=cfg).p_fill_this_epoch
    p_b = predict(PredictInput(depth_from_mark_ticks=depth_b, **base), sqlite_path=db, config=cfg).p_fill_this_epoch
    if depth_a > depth_b:
        assert p_a <= p_b + 1e-9
    else:
        assert p_b <= p_a + 1e-9


@given(
    q_a=st.integers(min_value=0, max_value=10**20),
    q_b=st.integers(min_value=0, max_value=10**20),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_predict_monotone_in_queue(tmp_path: Path, q_a: int, q_b: int) -> None:
    """T-02-P-04 — increasing queue_ahead → non-increasing p."""
    db = tmp_path / "state.sqlite"
    _seed_fit(db)
    cfg = _tiny_config()
    feats = _default_features()
    base = dict(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=5,
        current_features=feats,
        time_to_epoch_end_s=3600.0,
        current_chain_ts=1_700_000_100,
    )
    p_a = predict(PredictInput(queue_ahead_wei=q_a, **base), sqlite_path=db, config=cfg).p_fill_this_epoch
    p_b = predict(PredictInput(queue_ahead_wei=q_b, **base), sqlite_path=db, config=cfg).p_fill_this_epoch
    if q_a > q_b:
        assert p_a <= p_b + 1e-9
    else:
        assert p_b <= p_a + 1e-9
