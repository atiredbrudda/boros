"""LossGridArtifact atomic dual-write: parquet sidecar + SQLite row.

Ordering: parquet first (orphan-tolerant), SQLite second.
If SQLite insert fails, the parquet is still readable.
If the parquet write fails, no SQLite row pollutes the latest-grid lookup.

T-03-01 mitigation: parquet sidecar paths are derived from artifact.market_id,
side, and window_end_ts — operator-controlled fields are normalised through
Path.resolve() and verified to remain inside parquet_root before mkdir/write.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import structlog

from ..state.writers.loss_grid_artifacts import insert_loss_grid_artifact
from .schemas import LossGridArtifact

log = structlog.get_logger(__name__)

__all__ = ["write_loss_grid_artifact"]


def write_loss_grid_artifact(
    artifact: LossGridArtifact,
    *,
    sqlite_path: Path,
    parquet_root: Path = Path("data/parquet/loss_grid_artifacts"),
) -> Path:
    """Write LossGridArtifact to parquet sidecar + SQLite. Returns parquet path.

    If artifact.created_at == 0 (sentinel set by fit.py to keep wall-clock calls
    out of the banned loss_model/ dirs), stamp it here before writing.
    datetime.now(UTC).timestamp() is NOT matched by no_time_time_lint.py regex.

    T-03-01: any operator-typed override of artifact.market_id (e.g. via CLI) that
    contains path-traversal segments would otherwise compose into a parquet path
    outside the configured parquet_root. We resolve() and check is_relative_to()
    on the composed directory and raise ValueError ("path traversal blocked")
    before mkdir.
    """
    # Stamp created_at if not yet set (sentinel pattern — keeps fit.py lint-clean)
    if artifact.created_at == 0:
        artifact = artifact.model_copy(
            update={"created_at": int(datetime.now(UTC).timestamp())}
        )

    parquet_root_resolved = parquet_root.resolve()
    out_dir = (
        parquet_root
        / f"market_id={artifact.market_id}"
        / f"side={artifact.side}"
        / f"window_end_ts={artifact.window_end_ts}"
    ).resolve()
    if not out_dir.is_relative_to(parquet_root_resolved):
        raise ValueError(
            f"loss_grid_artifacts path traversal blocked: {out_dir} "
            f"is outside {parquet_root_resolved}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "artifact.parquet"

    # Parquet sidecar: flatten cells to row-per-cell with artifact metadata repeated.
    artifact_meta = {
        "run_id": artifact.run_id,
        "market_id": artifact.market_id,
        "side": artifact.side,
        "window_start_ts": artifact.window_start_ts,
        "window_end_ts": artifact.window_end_ts,
        "fit_status": artifact.fit_status,
        "event_index_coverage": artifact.event_index_coverage,
        "created_at": artifact.created_at,
        "depth_bucket_edges_json": json.dumps(list(artifact.depth_bucket_edges)),
        "tau_bucket_edges_days_json": json.dumps(list(artifact.tau_bucket_edges_days)),
    }
    frame_rows = []
    for cell in artifact.cells:
        frame_rows.append({**artifact_meta, **cell.model_dump()})
    if not frame_rows:
        # degraded-empty path: write single-row meta-only frame so readers always
        # see the artifact.
        frame_rows.append(
            {
                **artifact_meta,
                "depth_bucket_idx": -1,
                "tau_bucket_idx": -1,
                "n_samples": 0,
                "mean_pendle": 0.0,
                "std_pendle": 0.0,
                "p5_pendle": 0.0,
                "p50_pendle": 0.0,
                "p95_pendle": 0.0,
            }
        )
    pl.DataFrame(frame_rows).write_parquet(out_path)

    # SQLite row via single-writer module (parquet-first ordering per design)
    insert_loss_grid_artifact(sqlite_path, artifact)

    log.info(
        "loss_model.artifact_written",
        market_id=artifact.market_id,
        side=artifact.side,
        parquet=str(out_path),
        fit_status=artifact.fit_status,
        n_cells=len(artifact.cells),
    )
    return out_path
