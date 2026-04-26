"""LOSS-01/02 fit + expected_loss tests (Plan 03-01, Task 2).

Test IDs:
- T-03-F-01: fit_status='ok' on full-coverage synthetic
- T-03-F-02: fit_status='degraded' on sparse input
- T-03-E-01: expected_loss exact-cell mode
- T-03-E-02: expected_loss nearest_neighbor fallback (+ warning)
- T-03-E-03: expected_loss coarse_bound fallback (+ warning) == screener.fill_loss_coarse_bound
- T-03-E-04: expected_loss raises LossModelNoFreshGridError on stale grid
- T-03-E-05: expected_loss returns PENDLE-units float (smoke)
- T-03-E-06: expected_loss raises LossModelNoFreshGridError on absent grid
- T-03-E-07: expected_loss raises ValueError on negative tau
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from boros_brain.config.schema import BotConfig, DataConfig, MarketCalibration
from boros_brain.loss_model.artifact import write_loss_grid_artifact
from boros_brain.loss_model.expected_loss import (
    LossModelNoFreshGridError,
    expected_loss,
)
from boros_brain.loss_model.fit import build_loss_grid_artifact_from_fills
from boros_brain.loss_model.schemas import (
    ExpectedLossInput,
    LossGridArtifact,
    LossGridCell,
    PerFillPnL,
)

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
        markets=[
            MarketCalibration(
                market_id=MARKET_ID,
                scale=1.0,
                s=1.0,
                clo_lower_thresh=0.0,
                clo_upper_thresh=1.0,
                fIndex_oracle_address="0x0000000000000000000000000000000000000099",
                maturity_ts=1_700_000_000 + 365 * 86400,
            )
        ],
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


def _make_fill(
    *,
    side: str = "long",
    depth_idx: int = 0,
    tau_days: float = 10.0,
    pnl: float = -0.01,
    block_ts: int = 1_700_000_000,
) -> PerFillPnL:
    return PerFillPnL(
        market_id=MARKET_ID,
        side=side,  # type: ignore[arg-type]
        fill_event_index=block_ts,
        fill_block_ts=block_ts,
        fill_rate=0.10,
        fill_size_float=1.0,
        # Land in bucket depth_idx for the default depth_bucket_edges
        # = [0, 1, 2, 4, 8, 16, 32, 10000].
        depth_from_mark_ticks=int([0, 1, 2, 4, 8, 16, 32][depth_idx]),
        tau_days=tau_days,
        close_rate=0.10,
        close_block_ts=block_ts + 30,
        close_latency_s=30.0,
        pnl_pendle=pnl,
        fee_taker_pendle=0.0,
        fee_settlement_pendle=0.0,
        fee_entrance_amortized_pendle=0.0,
        fee_gas_pendle=0.0,
    )


def test_fit_health_gate_passes_on_full_grid() -> None:
    """T-03-F-01 — many fills uniformly across cells → fit_status='ok'."""
    config = _tiny_config()
    fills = []
    # 7 depth × 6 tau × 10 fills = 420 fills, comfortably over min_samples_per_cell=5
    for d_idx in range(7):
        for t_idx in range(6):
            for _k in range(10):
                fills.append(
                    _make_fill(
                        depth_idx=d_idx,
                        tau_days=float([3.0, 10.0, 20.0, 45.0, 75.0, 120.0][t_idx]),
                        pnl=-0.01 - 0.001 * d_idx,
                        block_ts=1_700_000_000 + len(fills) * 60,
                    )
                )
    artifact = build_loss_grid_artifact_from_fills(
        fills=fills,
        config=config,
        market_id=MARKET_ID,
        side="long",
        window_start_ts=0,
        window_end_ts=1_700_000_000,
        run_id="test-run-fit-ok",
    )
    assert (
        artifact.fit_status == "ok"
    ), f"expected ok; cells: {[(c.depth_bucket_idx, c.tau_bucket_idx, c.n_samples) for c in artifact.cells]}"
    assert len(artifact.cells) == 42  # 7 depth × 6 tau cells populated


def test_fit_degrades_on_sparse() -> None:
    """T-03-F-02 — 3 fills total → fit_status='degraded'; no exception."""
    config = _tiny_config()
    fills = [_make_fill(block_ts=1_700_000_000 + k) for k in range(3)]
    artifact = build_loss_grid_artifact_from_fills(
        fills=fills,
        config=config,
        market_id=MARKET_ID,
        side="long",
        window_start_ts=0,
        window_end_ts=1_700_000_000,
        run_id="test-run-fit-degraded",
    )
    assert artifact.fit_status == "degraded"


def _seed_full_grid_artifact(db: Path, parquet_root: Path, *, window_end_ts: int) -> str:
    """Seed a full-coverage artifact for expected_loss tests. Returns run_id."""
    cells = []
    for d_idx in range(7):
        for t_idx in range(6):
            cells.append(
                LossGridCell(
                    depth_bucket_idx=d_idx,
                    tau_bucket_idx=t_idx,
                    n_samples=10,
                    mean_pendle=-0.01 - 0.001 * d_idx,
                    std_pendle=0.002,
                    p5_pendle=-0.02 - 0.001 * d_idx,
                    p50_pendle=-0.01 - 0.001 * d_idx,
                    p95_pendle=-0.005 - 0.001 * d_idx,
                )
            )
    artifact = LossGridArtifact(
        run_id="seed-full-001",
        market_id=MARKET_ID,
        side="long",
        window_start_ts=window_end_ts - 90 * 86400,
        window_end_ts=window_end_ts,
        fit_status="ok",
        depth_bucket_edges=[0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0],
        tau_bucket_edges_days=[0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0],
        cells=cells,
        event_index_coverage="full",
        created_at=0,
    )
    write_loss_grid_artifact(artifact, sqlite_path=db, parquet_root=parquet_root)
    return artifact.run_id


def test_expected_loss_exact_mode(tmp_path: Path) -> None:
    """T-03-E-01 — full-coverage artifact → fallback_mode='exact'."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    window_end_ts = 1_700_000_000
    _seed_full_grid_artifact(db, tmp_path / "parquet", window_end_ts=window_end_ts)

    config = _tiny_config()
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=4,  # bucket idx 3
        time_to_maturity_s=20 * 86400,  # tau_days = 20 → bucket idx 2
        current_chain_ts=window_end_ts + 60,
    )
    out = expected_loss(req, sqlite_path=db, config=config)
    assert out.fallback_mode == "exact"
    assert out.cell_n_samples == 10
    assert out.expected_loss_pendle < 0  # all cells loss-dominant
    assert out.fit_status == "ok"


def test_expected_loss_nearest_neighbor(tmp_path: Path) -> None:
    """T-03-E-02 — target cell empty but a nearby populated cell satisfies k-NN."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    # Build an artifact where ONLY one cell is populated (the rest are absent
    # from artifact.cells — model treats absent cells as n=0).
    window_end_ts = 1_700_000_000
    artifact = LossGridArtifact(
        run_id="seed-knn-001",
        market_id=MARKET_ID,
        side="long",
        window_start_ts=window_end_ts - 90 * 86400,
        window_end_ts=window_end_ts,
        fit_status="degraded",
        depth_bucket_edges=[0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0],
        tau_bucket_edges_days=[0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0],
        cells=[
            LossGridCell(
                depth_bucket_idx=2,
                tau_bucket_idx=2,
                n_samples=20,
                mean_pendle=-0.05,
                std_pendle=0.01,
                p5_pendle=-0.07,
                p50_pendle=-0.05,
                p95_pendle=-0.03,
            )
        ],
        event_index_coverage="full",
        created_at=0,
    )
    write_loss_grid_artifact(artifact, sqlite_path=db, parquet_root=tmp_path / "parquet")

    config = _tiny_config()
    # Target = depth_bucket 3, tau_bucket 3 — adjacent to (2,2). dist = sqrt(2) ~ 1.41
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=4,  # bucket idx 3
        time_to_maturity_s=45 * 86400,  # bucket idx 3
        current_chain_ts=window_end_ts + 60,
    )
    with structlog.testing.capture_logs() as captured:
        out = expected_loss(req, sqlite_path=db, config=config)

    assert out.fallback_mode == "nearest_neighbor"
    assert out.cell_n_samples == 20
    events = [r["event"] for r in captured]
    assert "loss_model.sparse_cell_fallback" in events, events


def test_expected_loss_coarse_bound(tmp_path: Path) -> None:
    """T-03-E-03 — no neighbor inside knn_max_distance → coarse_bound fallback."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    # Only one populated cell, far from the target.
    window_end_ts = 1_700_000_000
    artifact = LossGridArtifact(
        run_id="seed-coarse-001",
        market_id=MARKET_ID,
        side="long",
        window_start_ts=window_end_ts - 90 * 86400,
        window_end_ts=window_end_ts,
        fit_status="degraded",
        depth_bucket_edges=[0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0],
        tau_bucket_edges_days=[0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0],
        cells=[
            LossGridCell(
                depth_bucket_idx=0,
                tau_bucket_idx=0,
                n_samples=20,
                mean_pendle=-0.05,
                std_pendle=0.01,
                p5_pendle=-0.07,
                p50_pendle=-0.05,
                p95_pendle=-0.03,
            )
        ],
        event_index_coverage="full",
        created_at=0,
    )
    write_loss_grid_artifact(artifact, sqlite_path=db, parquet_root=tmp_path / "parquet")

    config = _tiny_config()
    # Target = (6, 5) — Euclidean dist to (0,0) = sqrt(61) ~ 7.81 > knn_max_distance=4.0.
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=64,  # bucket idx 6 (terminal)
        time_to_maturity_s=120 * 86400,  # bucket idx 5
        current_chain_ts=window_end_ts + 60,
    )
    with structlog.testing.capture_logs() as captured:
        out = expected_loss(req, sqlite_path=db, config=config)

    assert out.fallback_mode == "coarse_bound"
    assert out.expected_loss_pendle == pytest.approx(config.screener.fill_loss_coarse_bound * 1.0)
    events = [r["event"] for r in captured]
    assert "loss_model.sparse_cell_fallback" in events, events


def test_expected_loss_raises_on_stale_grid(tmp_path: Path) -> None:
    """T-03-E-04 — grid older than fit_max_staleness_s → LossModelNoFreshGridError."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    window_end_ts = 1_700_000_000
    _seed_full_grid_artifact(db, tmp_path / "parquet", window_end_ts=window_end_ts)

    config = _tiny_config()
    # Default fit_max_staleness_s = 86400 (1 day). Use 3 days in the future.
    current_chain_ts = window_end_ts + 3 * 86400
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=4,
        time_to_maturity_s=20 * 86400,
        current_chain_ts=current_chain_ts,
    )
    with pytest.raises(LossModelNoFreshGridError, match="stale"):
        expected_loss(req, sqlite_path=db, config=config)


def test_expected_loss_returns_pendle_units(tmp_path: Path) -> None:
    """T-03-E-05 — output is a float; smoke test for unit consistency."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    window_end_ts = 1_700_000_000
    _seed_full_grid_artifact(db, tmp_path / "parquet", window_end_ts=window_end_ts)

    config = _tiny_config()
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=2,
        time_to_maturity_s=10 * 86400,
        current_chain_ts=window_end_ts + 60,
    )
    out = expected_loss(req, sqlite_path=db, config=config)
    assert isinstance(out.expected_loss_pendle, float)
    assert isinstance(out.cell_p50_pendle, float)
    assert isinstance(out.cell_p95_pendle, float)


def test_expected_loss_raises_on_no_artifact(tmp_path: Path) -> None:
    """T-03-E-06 — empty state → LossModelNoFreshGridError."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    config = _tiny_config()
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=4,
        time_to_maturity_s=20 * 86400,
        current_chain_ts=1_700_000_000,
    )
    with pytest.raises(LossModelNoFreshGridError):
        expected_loss(req, sqlite_path=db, config=config)


def test_expected_loss_negative_tau_raises(tmp_path: Path) -> None:
    """T-03-E-07 — negative tau → ValueError (Phase 4 SAFE-07 already broke earlier)."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    config = _tiny_config()
    req = ExpectedLossInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=4,
        time_to_maturity_s=-1,
        current_chain_ts=1_700_000_000,
    )
    with pytest.raises(ValueError, match="negative tau"):
        expected_loss(req, sqlite_path=db, config=config)
