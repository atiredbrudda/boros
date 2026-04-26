"""FILL-01 NHPP fit tests (Plan 02-03).

Test IDs: T-02-M-01 through T-02-M-02.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from boros_brain.config.schema import BotConfig, DataConfig
from boros_brain.fill_model.fit import fit_market_side
from boros_brain.fill_model.schemas import FitArtifact

FIXTURES = Path(__file__).parent / "fixtures"
MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"

# β_true from _generate_fill_model_fixtures.py — must match the generator exactly
BETA_TRUE = [-1.0, 0.5, -0.3, 0.1, 0.1, 0.2]


def _tiny_config() -> BotConfig:
    return BotConfig(
        mode="backtest",
        strategy_version="test",
        market_id=MARKET_ID,
        side="long",
        root_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        data=DataConfig(rpc_url_arbitrum="https://example.com"),
    )  # uses default screener + fill_model


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def test_fit_converges_on_synthetic_poisson(tmp_path: Path) -> None:
    """T-02-M-01 — synthetic Poisson with known β; assert fit converges + β_hat close to β_true."""
    df = pl.read_parquet(FIXTURES / "fill_model_synthetic_poisson.parquet")
    # Fixture has single market/side; relabel to match the fixed MARKET_ID
    df = df.with_columns(pl.lit(MARKET_ID).alias("market_id"), pl.lit("long").alias("side"))

    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    config = _tiny_config()
    artifact = fit_market_side(
        features_df=df,
        market_id=MARKET_ID,
        side="long",
        config=config,
        run_id="test-run-001",
        sqlite_path=db,
    )

    assert isinstance(artifact, FitArtifact)
    assert artifact.converged is True, f"fit did not converge; status={artifact.fit_status}"
    assert artifact.fit_status == "ok", f"unexpected status={artifact.fit_status}"

    # β has length 1 + len(covariate_whitelist)
    assert len(artifact.beta) == 1 + len(artifact.covariate_whitelist)

    # Non-intercept coefficients within 3 × stderr of β_true (loose — sampling variance on 2000 bins)
    for i, (bhat, bse, btrue) in enumerate(zip(artifact.beta, artifact.beta_stderr, BETA_TRUE, strict=False)):
        if i == 0:
            continue  # intercept has a wider tolerance due to exposure normalization
        assert abs(bhat - btrue) < 3.0 * max(bse, 0.05), f"β[{i}] = {bhat} outside 3·SE of {btrue} (SE={bse})"


def test_fit_degrades_on_sparse(tmp_path: Path) -> None:
    """T-02-M-02 — 10-row input (below min_events_per_param_ratio*params=60) → fit_status='degraded' + no crash."""
    n = 10
    df = pl.DataFrame(
        {
            "market_id": [MARKET_ID] * n,
            "side": ["long"] * n,
            "bin_start": list(range(n)),
            "trade_count": [0, 1, 0, 2, 1, 0, 0, 1, 2, 0],
            "basis_spread": [0.1] * n,
            "imbalance": [0.0] * n,
            "sin_settlement": [0.0] * n,
            "cos_settlement": [1.0] * n,
            "ewma_vol": [0.1] * n,
            "bin_duration_s": [60.0] * n,
        }
    )

    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    config = _tiny_config()
    artifact = fit_market_side(
        features_df=df,
        market_id=MARKET_ID,
        side="long",
        config=config,
        run_id="test-run-sparse",
        sqlite_path=db,
    )
    # Either the fit converges but too-few-events gate declares degraded, or it doesn't converge — both OK
    assert artifact.fit_status == "degraded"
    # Must NOT crash — FitArtifact was constructed and persisted
    assert len(artifact.beta) == 1 + len(artifact.covariate_whitelist)


def test_covariate_whitelist_covered_in_features_test() -> None:
    """T-02-F-01 note: covariate whitelist validation is covered in
    test_fill_model_features.py::test_covariate_whitelist.
    This stub documents that the coverage is intentionally in the features test,
    not here, to avoid duplication.
    """
    # See test_fill_model_features.py::test_covariate_whitelist for T-02-F-01.
    pass
