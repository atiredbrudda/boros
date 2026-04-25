"""Shared pytest fixtures for the boros_brain test suite."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Literal

import pytest

from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig

# repo root (python/tests → python/ → repo root)
ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Phase 4 Plan 04-01: apply_migrations helper (NOT a fixture — module-level
# helper so test helpers can call it directly without a fixture dependency).
# Mirrors test_fill_model_predict_contract.py lines 37-46.
# ---------------------------------------------------------------------------

def apply_migrations(db: Path) -> None:
    """Run alembic migrations to head against db. Mirrors test_fill_model_predict_contract.py."""
    from alembic import command
    from alembic.config import Config

    ALEMBIC_DIR = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations"
    cfg = Config(str(ALEMBIC_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


@pytest.fixture
def default_yaml_path() -> Path:
    return ROOT / "strategy" / "v0.5-default.yaml"


@pytest.fixture
def default_config(default_yaml_path: Path) -> BotConfig:
    """strategy/v0.5-default.yaml uses placeholder wallet strings (TBD).

    Those satisfy the `str` type — Phase 8 will add a live-mode pre-deploy
    validator that rejects placeholder values when `mode == 'live'`.
    """
    return load_config(default_yaml_path)


@pytest.fixture
def tmp_sqlite_path(tmp_path: Path) -> Path:
    """Isolated SQLite DB per test. Used once plan 01-02 lands DB code."""
    return tmp_path / "test_state.sqlite"


@pytest.fixture
def frozen_chain_time() -> int:
    """Deterministic chain timestamp for tests. Used once INFRA-14 code lands."""
    return 1714089600  # 2026-04-26T00:00:00Z


@pytest.fixture
def ipc_dir() -> Path:
    """Short-path temp dir under /tmp so ZMQ ipc:// endpoints stay under the
    macOS 103-byte sockaddr_un.sun_path limit.

    pytest's `tmp_path` resolves to `/private/var/folders/.../pytest-of-…/pytest-N/…`
    which can easily exceed 103 chars and makes `zmq.PUB.bind('ipc://…')` fail
    with `ZMQError: ipc path is longer than 103 characters`.
    """
    base = Path(tempfile.gettempdir())
    # 8-char uuid suffix — keeps each fixture unique without exhausting sun_path.
    d = base / f"b_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 4 Plan 04-01 — seed-helper fixture-factories for breaker tests.
#
# Pattern: each fixture returns an *inner function* so the test can call it
# with test-specific parameters (slope, n, rows, etc.) and get back the
# sqlite_path (or parquet_root) that was populated.
#
# Writer imports are deferred INSIDE the inner functions (not at module top)
# so this conftest itself imports cleanly even before Plan 04-02 lands the
# margin_history / breaker_events / predeploy_gate_records writers.
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_margin_history(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for margin_history rows.

    Returns a callable: _seed(slope, n, market_id, base_chain_ts) -> Path.
    Applies migrations then inserts n rows with net_margin_usd = 100 + slope*i.

    Writer import is deferred — lands in Plan 04-02.
    """

    def _seed(
        slope: float,
        n: int = 20,
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
        base_chain_ts: int = 1_700_000_000,
    ) -> Path:
        from boros_brain.state.writers.margin_history import insert_margin_snapshot
        from boros_brain.state.db import open_connection

        apply_migrations(tmp_sqlite_path)
        with open_connection(tmp_sqlite_path) as conn:
            for i in range(n):
                insert_margin_snapshot(
                    conn,
                    chain_ts=base_chain_ts + i,
                    market_id=market_id,
                    net_margin_usd=100.0 + slope * i,
                    maintenance_margin_usd=10.0,
                    available_collateral_usd=200.0,
                    run_id="test-001",
                )
            conn.commit()
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_clo_history(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for clo_history rows.

    Returns a callable: _seed(rows, market_id) -> Path where
    rows: list[tuple[snapshot_ts, clo_lower_thresh, clo_upper_thresh]].
    """

    def _seed(
        rows: list[tuple[int, float, float]],
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
    ) -> Path:
        from boros_brain.state.writers.clo_history import insert_clo_snapshot
        from boros_brain.state.db import open_connection

        apply_migrations(tmp_sqlite_path)
        with open_connection(tmp_sqlite_path) as conn:
            for snapshot_ts, clo_lower_thresh, clo_upper_thresh in rows:
                insert_clo_snapshot(
                    conn,
                    snapshot_ts=snapshot_ts,
                    market_id=market_id,
                    clo_lower_thresh=clo_lower_thresh,
                    clo_upper_thresh=clo_upper_thresh,
                )
            conn.commit()
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_competition_history(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for competition_history rows.

    Returns a callable: _seed(rows, market_id) -> Path where
    rows: list[tuple[polled_at_utc, chain_ts, q_me_pendle, sigma_others_pendle]].
    """

    def _seed(
        rows: list[tuple[str, int, float, float]],
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
    ) -> Path:
        from boros_brain.state.writers.competition_history import insert_competition_row
        from boros_brain.state.db import open_connection

        apply_migrations(tmp_sqlite_path)
        with open_connection(tmp_sqlite_path) as conn:
            for polled_at_utc, chain_ts, q_me_pendle, sigma_others_pendle in rows:
                insert_competition_row(
                    conn,
                    polled_at_utc=polled_at_utc,
                    chain_ts=chain_ts,
                    market_id=market_id,
                    q_me_pendle=q_me_pendle,
                    sigma_others_pendle=sigma_others_pendle,
                    run_id="test-001",
                    data_source="live",
                )
            conn.commit()
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_market_reward_calibration(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for market_reward_calibration rows.

    Returns a callable: _seed(rows) -> Path where
    rows: list[dict] with keys matching insert_market_reward_calibration kwargs.
    """

    def _seed(rows: list[dict]) -> Path:
        from boros_brain.state.writers.market_reward_calibration import (
            insert_market_reward_calibration,
        )

        apply_migrations(tmp_sqlite_path)
        for row in rows:
            insert_market_reward_calibration(
                tmp_sqlite_path,
                run_id=row.get("run_id", "test-001"),
                **{k: v for k, v in row.items() if k != "run_id"},
            )
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_loss_grid_artifact(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for loss_grid_artifacts rows.

    Returns a callable: _seed(fit_status, market_id, side) -> Path.
    Inserts a minimal LossGridArtifact with the given fit_status.
    """

    def _seed(
        fit_status: Literal["ok", "degraded", "stale"] = "ok",
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
        side: str = "long",
    ) -> Path:
        from boros_brain.state.writers.loss_grid_artifacts import insert_loss_grid_artifact
        from boros_brain.loss_model.schemas import LossGridArtifact

        apply_migrations(tmp_sqlite_path)
        artifact = LossGridArtifact(
            run_id="test-001",
            market_id=market_id,
            side=side,
            window_start_ts=1_699_000_000,
            window_end_ts=1_700_000_000,
            fit_status=fit_status,
            depth_bucket_edges=[0, 5, 10, 20],
            tau_bucket_edges_days=[0.0, 7.0, 30.0],
            cells=[],
            event_index_coverage="full",
            created_at=1_700_000_000,
        )
        insert_loss_grid_artifact(tmp_sqlite_path, artifact)
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_fill_model_fit(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for fill_model_fits rows.

    Returns a callable: _seed(market_id, side, fit_window_end_ts) -> Path.
    Inserts a minimal FitArtifact with a single covariate ('basis_spread') so
    that engine tests can pass current_features={'basis_spread': 0.01} and have
    predict() succeed without raising FillModelNoFreshFitError.

    Added in Plan 04-03 as a Rule 2 auto-add: the decision engine tests require
    both a loss grid and a fill model fit to be seeded for evaluate() to return
    without propagating FillModel*Error.
    """

    def _seed(
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
        side: str = "long",
        fit_window_end_ts: int = 1_700_000_000,
    ) -> Path:
        from boros_brain.fill_model.schemas import FitArtifact
        from boros_brain.state.writers.fill_model_fits import insert_fit_artifact

        apply_migrations(tmp_sqlite_path)
        artifact = FitArtifact(
            run_id="test-fill-fit-001",
            fit_window_start_ts=fit_window_end_ts - 14 * 86400,
            fit_window_end_ts=fit_window_end_ts,
            market_id=market_id,
            side=side,  # type: ignore[arg-type]
            covariate_whitelist=["basis_spread"],
            beta=[-2.0, 0.1],  # intercept + 1 feature → low lambda → low p_fill
            beta_stderr=[0.1, 0.05],
            log_likelihood=-200.0,
            deviance=400.0,
            aic=404.0,
            n_observations=5000,
            converged=True,
            fit_status="ok",
            event_index_coverage="full",
            created_at=fit_window_end_ts,
        )
        insert_fit_artifact(tmp_sqlite_path, artifact)
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_tx_receipts_fills(tmp_sqlite_path: Path) -> Callable:
    """Fixture-factory for tx_receipts rows with event_type='fill'.

    Returns a callable: _seed(n_fills, since_chain_ts, market_id) -> Path.

    NOTE: depends on the event_type column added by Plan 04-02 migration.
    Uses TEST_ONLY=True writer path.
    """

    def _seed(
        n_fills: int,
        since_chain_ts: int,
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
    ) -> Path:
        from boros_brain.state.db import open_connection

        apply_migrations(tmp_sqlite_path)
        with open_connection(tmp_sqlite_path) as conn:
            for i in range(n_fills):
                conn.execute(
                    "INSERT INTO tx_receipts "
                    "(tx_hash, run_id, submitted_at_ts, confirmed_at_ts, status, "
                    " gas_used, intent, related_order_id, "
                    " event_type, chain_ts, market_id, order_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"0x{'a' * 62}{i:02d}",   # unique tx_hash (PK)
                        "test-001",
                        since_chain_ts + i,         # submitted_at_ts (required NOT NULL)
                        since_chain_ts + i + 1,     # confirmed_at_ts
                        "confirmed",                # status (required NOT NULL)
                        None,                       # gas_used
                        "close",                    # intent (required NOT NULL)
                        None,                       # related_order_id
                        "fill",                     # event_type
                        since_chain_ts + i,         # chain_ts (SAFE-05 window filter)
                        market_id,                  # market_id
                        f"ord-fill-{i}",            # order_id
                    ),
                )
            conn.commit()
        return tmp_sqlite_path

    return _seed


@pytest.fixture
def seed_underlying_apr_parquet(tmp_path: Path) -> Callable:
    """Fixture-factory for underlying_apr parquet snapshots.

    Returns a callable: _seed(last_ts, exchange, symbol, parquet_root) -> Path.
    Writes a minimal polars DataFrame to the Hive-partitioned parquet layout.
    """

    def _seed(
        last_ts: int,
        exchange: str = "binance",
        symbol: str = "ETHUSDT",
        parquet_root: Path | None = None,
    ) -> Path:
        import polars as pl

        root = parquet_root if parquet_root is not None else tmp_path / "parquet"
        out_dir = root / "underlying_apr" / f"exchange={exchange}" / f"symbol={symbol}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "snapshot.parquet"
        pl.DataFrame({"snapshot_ts": [last_ts], "rate": [0.0001]}).write_parquet(out_file)
        return root

    return _seed
