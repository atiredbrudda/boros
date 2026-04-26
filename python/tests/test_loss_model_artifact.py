"""LOSS-01 artifact dual-write tests (Plan 03-01, Task 2).

Test IDs:
- T-03-A-01: dual-write atomicity (parquet + SQLite round-trip)
- T-03-A-02: sentinel created_at stamping
- T-03-A-03: T-03-01 path-traversal mitigation
- T-03-A-04: UPSERT idempotency on (market_id, side, window_end_ts)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.loss_model.artifact import write_loss_grid_artifact
from boros_brain.loss_model.schemas import LossGridArtifact, LossGridCell
from boros_brain.state.writers.loss_grid_artifacts import (
    get_latest_loss_grid,
    insert_loss_grid_artifact,
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


def _make_cells() -> list[LossGridCell]:
    return [
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
        LossGridCell(
            depth_bucket_idx=1,
            tau_bucket_idx=2,
            n_samples=8,
            mean_pendle=-0.02,
            std_pendle=0.006,
            p5_pendle=-0.03,
            p50_pendle=-0.02,
            p95_pendle=-0.01,
        ),
    ]


def _make_artifact(*, market_id: str = "BINANCE-ETHUSDT-29MAY2026") -> LossGridArtifact:
    return LossGridArtifact(
        run_id="test-run-001",
        market_id=market_id,
        side="long",
        window_start_ts=1_700_000_000 - 90 * 86400,
        window_end_ts=1_700_000_000,
        fit_status="ok",
        depth_bucket_edges=[0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0],
        tau_bucket_edges_days=[0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0],
        cells=_make_cells(),
        event_index_coverage="full",
        created_at=0,  # sentinel — write_loss_grid_artifact stamps
    )


def test_dual_write_atomicity(tmp_path: Path) -> None:
    """T-03-A-01 — parquet + SQLite round-trip atomically; round-trip schema preserved."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    artifact = _make_artifact()
    parquet_root = tmp_path / "parquet"

    out_path = write_loss_grid_artifact(artifact, sqlite_path=db, parquet_root=parquet_root)
    assert out_path.exists(), f"parquet missing at {out_path}"
    assert out_path.stat().st_size > 0

    # Read back via single-writer get_latest_loss_grid
    latest = get_latest_loss_grid(db, artifact.market_id, "long")
    assert latest is not None
    assert latest.run_id == artifact.run_id
    assert latest.market_id == artifact.market_id
    assert latest.side == "long"
    assert latest.window_start_ts == artifact.window_start_ts
    assert latest.window_end_ts == artifact.window_end_ts
    assert latest.fit_status == "ok"
    assert latest.depth_bucket_edges == artifact.depth_bucket_edges
    assert latest.tau_bucket_edges_days == artifact.tau_bucket_edges_days
    assert len(latest.cells) == len(artifact.cells)
    assert latest.cells[0].n_samples == artifact.cells[0].n_samples
    assert latest.cells[0].mean_pendle == pytest.approx(artifact.cells[0].mean_pendle)
    assert latest.event_index_coverage == "full"


def test_sentinel_created_at_stamped(tmp_path: Path) -> None:
    """T-03-A-02 — pass created_at=0; round-trip carries a real timestamp."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    artifact = _make_artifact()
    assert artifact.created_at == 0
    parquet_root = tmp_path / "parquet"
    write_loss_grid_artifact(artifact, sqlite_path=db, parquet_root=parquet_root)

    latest = get_latest_loss_grid(db, artifact.market_id, "long")
    assert latest is not None
    assert latest.created_at > 0, f"sentinel not stamped: {latest.created_at}"


def test_path_traversal_rejected(tmp_path: Path) -> None:
    """T-03-A-03 / T-03-01 — operator-typed market_id with '..' segments raises ValueError."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    parquet_root = tmp_path / "parquet"

    bad_artifact = LossGridArtifact(
        run_id="bad",
        market_id="../../../etc/passwd",  # T-03-01 attempt
        side="long",
        window_start_ts=0,
        window_end_ts=1_700_000_000,
        fit_status="ok",
        depth_bucket_edges=[0.0, 10000.0],
        tau_bucket_edges_days=[0.0, 10000.0],
        cells=_make_cells(),
        event_index_coverage="full",
        created_at=0,
    )
    with pytest.raises(ValueError, match="path traversal blocked"):
        write_loss_grid_artifact(bad_artifact, sqlite_path=db, parquet_root=parquet_root)


def test_upsert_idempotent(tmp_path: Path) -> None:
    """T-03-A-04 — same (market_id, side, window_end_ts) twice → row count == 1."""
    import sqlite3

    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    artifact = _make_artifact()
    # Stamp created_at by hand (insert_loss_grid_artifact does NOT stamp;
    # the sentinel-stamp lives in artifact.write_loss_grid_artifact).
    artifact_v1 = artifact.model_copy(update={"created_at": 1_700_000_001})
    insert_loss_grid_artifact(db, artifact_v1)

    # Re-insert with a different run_id but same PK → UPDATE, not duplicate
    artifact_v2 = artifact_v1.model_copy(update={"run_id": "test-run-002", "created_at": 1_700_000_002})
    insert_loss_grid_artifact(db, artifact_v2)

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM loss_grid_artifacts").fetchone()[0]
    assert n == 1, f"expected upsert; got {n} rows"
    # Latest row reflects the second write
    latest = get_latest_loss_grid(db, artifact.market_id, "long")
    assert latest is not None
    assert latest.run_id == "test-run-002"
    assert latest.created_at == 1_700_000_002
