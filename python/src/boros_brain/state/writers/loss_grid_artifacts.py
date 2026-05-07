"""Single writer for the `loss_grid_artifacts` table (brain-owned).

PROTO-02 single-writer discipline. Only `brain.loss_model.artifact.write_loss_grid_artifact`
imports `insert_loss_grid_artifact`. `brain.loss_model.expected_loss.expected_loss`
imports `get_latest_loss_grid` (read, not write — lint doesn't care).

Any `INSERT INTO loss_grid_artifacts` / `UPDATE loss_grid_artifacts` /
`DELETE FROM loss_grid_artifacts` outside this module triggers
scripts/sqlite_writer_lint.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from boros_brain.state.db import open_connection

from ...loss_model.schemas import LossGridArtifact, LossGridCell

log = structlog.get_logger(__name__)

__all__ = ["insert_loss_grid_artifact", "get_latest_loss_grid"]


def insert_loss_grid_artifact(sqlite_path: Path, artifact: LossGridArtifact) -> None:
    """Insert (or upsert on PK conflict) one loss-grid artifact. Self-contained
    — manages its own connection."""
    with open_connection(sqlite_path) as conn:
        conn.execute(
            """
            INSERT INTO loss_grid_artifacts (
                run_id, market_id, side, window_start_ts, window_end_ts,
                fit_status, depth_bucket_edges, tau_bucket_edges_days,
                cells_json, event_index_coverage, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id, side, window_end_ts) DO UPDATE SET
                run_id = excluded.run_id,
                window_start_ts = excluded.window_start_ts,
                fit_status = excluded.fit_status,
                depth_bucket_edges = excluded.depth_bucket_edges,
                tau_bucket_edges_days = excluded.tau_bucket_edges_days,
                cells_json = excluded.cells_json,
                event_index_coverage = excluded.event_index_coverage,
                created_at = excluded.created_at
            """,
            (
                artifact.run_id,
                artifact.market_id,
                artifact.side,
                artifact.window_start_ts,
                artifact.window_end_ts,
                artifact.fit_status,
                json.dumps(list(artifact.depth_bucket_edges)),
                json.dumps(list(artifact.tau_bucket_edges_days)),
                json.dumps([c.model_dump() for c in artifact.cells]),
                artifact.event_index_coverage,
                artifact.created_at,
            ),
        )
    log.info(
        "loss_model.artifact_persisted",
        market_id=artifact.market_id,
        side=artifact.side,
        window_end_ts=artifact.window_end_ts,
        fit_status=artifact.fit_status,
        n_cells=len(artifact.cells),
    )


def get_latest_loss_grid(
    sqlite_path: Path,
    market_id: str,
    side: str,
    *,
    current_chain_ts: int | None = None,
) -> LossGridArtifact | None:
    """Return the most-recent-by-window_end_ts artifact for (market_id, side).

    Args:
        sqlite_path: Path to state SQLite DB.
        market_id: Market identifier (e.g. ``BINANCE-ETHUSDT-25SEP2026``).
        side: ``"long"`` or ``"short"``.
        current_chain_ts: Optional chain-time upper bound. ``None`` = live mode
            (unbounded SELECT — absolute latest by ``window_end_ts DESC``).
            Backtest replay MUST pass the current tick's ``chain_ts`` to prevent
            look-ahead bias from cross-run artifact accumulation. See
            ``[[loss-model-expected-loss-look-ahead-read-path]]``.
    """
    base_sql = (
        "SELECT run_id, market_id, side, window_start_ts, window_end_ts, "
        "fit_status, depth_bucket_edges, tau_bucket_edges_days, "
        "cells_json, event_index_coverage, created_at "
        "FROM loss_grid_artifacts "
        "WHERE market_id = ? AND side = ?"
    )
    params: tuple[object, ...] = (market_id, side)
    if current_chain_ts is not None:
        base_sql += " AND window_end_ts <= ?"
        params = (market_id, side, int(current_chain_ts))
    base_sql += " ORDER BY window_end_ts DESC LIMIT 1"
    with open_connection(sqlite_path) as conn:
        row = conn.execute(base_sql, params).fetchone()
    if row is None:
        return None
    cells_payload = json.loads(row[8])
    cells = [LossGridCell(**c) for c in cells_payload]
    return LossGridArtifact(
        run_id=row[0],
        market_id=row[1],
        side=row[2],
        window_start_ts=row[3],
        window_end_ts=row[4],
        fit_status=row[5],
        depth_bucket_edges=json.loads(row[6]),
        tau_bucket_edges_days=json.loads(row[7]),
        cells=cells,
        event_index_coverage=row[9],
        created_at=row[10],
    )
