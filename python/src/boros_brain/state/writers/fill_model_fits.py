"""Single writer for the `fill_model_fits` table (brain-owned).

PROTO-02 single-writer discipline. Only `brain.fill_model.artifact.write_fit_artifact`
imports insert_fit_artifact. `brain.fill_model.predict.predict` imports `get_latest_fit`
(read, not write — lint doesn't care).

Any `INSERT INTO fill_model_fits` / `UPDATE fill_model_fits` / `DELETE FROM fill_model_fits`
outside this module triggers scripts/sqlite_writer_lint.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from boros_brain.state.db import open_connection

from ...fill_model.schemas import FitArtifact

log = structlog.get_logger(__name__)

__all__ = ["insert_fit_artifact", "get_latest_fit"]


def _nan_to_sentinel(v: float | None, sentinel: float = -1.0) -> float | None:
    """Return sentinel for NaN floats (SQLite NOT NULL columns reject NaN as NULL).

    Used for log_likelihood, deviance, aic in degraded fit artifacts where these
    are set to float('nan') as a placeholder. The sentinel -1.0 is unambiguous
    (log-likelihoods are negative; AIC/deviance are non-negative for real fits).
    NULL-able columns (gof_ks_pval, gof_lr_vs_null) are left None — they are
    allowed NULL in the schema and never set to NaN by the caller.
    """
    import math

    if v is None or math.isnan(v):
        return sentinel
    return v


def insert_fit_artifact(sqlite_path: Path, artifact: FitArtifact) -> None:
    """Insert one fit artifact. Self-contained — manages its own connection."""
    with open_connection(sqlite_path) as conn:
        conn.execute(
            """
            INSERT INTO fill_model_fits (
                run_id, fit_window_start_ts, fit_window_end_ts, market_id, side,
                covariate_whitelist, beta, beta_stderr,
                log_likelihood, deviance, aic, n_observations, converged, fit_status,
                gof_ks_pval, gof_lr_vs_null, event_index_coverage, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id, side, fit_window_end_ts) DO UPDATE SET
                run_id = excluded.run_id,
                fit_window_start_ts = excluded.fit_window_start_ts,
                covariate_whitelist = excluded.covariate_whitelist,
                beta = excluded.beta,
                beta_stderr = excluded.beta_stderr,
                log_likelihood = excluded.log_likelihood,
                deviance = excluded.deviance,
                aic = excluded.aic,
                n_observations = excluded.n_observations,
                converged = excluded.converged,
                fit_status = excluded.fit_status,
                gof_ks_pval = excluded.gof_ks_pval,
                gof_lr_vs_null = excluded.gof_lr_vs_null,
                event_index_coverage = excluded.event_index_coverage,
                created_at = excluded.created_at
            """,
            (
                artifact.run_id,
                artifact.fit_window_start_ts,
                artifact.fit_window_end_ts,
                artifact.market_id,
                artifact.side,
                json.dumps(artifact.covariate_whitelist),
                json.dumps(artifact.beta),
                json.dumps(artifact.beta_stderr),
                # Phase 05.5 fix: NOT NULL columns reject float('nan') as NULL.
                # Degraded artifacts carry NaN for these stats — coerce to sentinel.
                _nan_to_sentinel(artifact.log_likelihood),
                _nan_to_sentinel(artifact.deviance),
                _nan_to_sentinel(artifact.aic),
                artifact.n_observations,
                1 if artifact.converged else 0,
                artifact.fit_status,
                artifact.gof_ks_pval,
                artifact.gof_lr_vs_null,
                artifact.event_index_coverage,
                artifact.created_at,
            ),
        )
    log.info(
        "fill_model.fit_artifact_persisted",
        market_id=artifact.market_id,
        side=artifact.side,
        fit_window_end_ts=artifact.fit_window_end_ts,
        fit_status=artifact.fit_status,
        n_observations=artifact.n_observations,
    )


def get_latest_fit(
    sqlite_path: Path,
    market_id: str,
    side: str,
    *,
    current_chain_ts: int | None = None,
) -> FitArtifact | None:
    """Return the most-recent-by-fit_window_end_ts artifact for (market_id, side).

    Args:
        sqlite_path: Path to state SQLite DB.
        market_id: Market identifier (e.g. ``BINANCE-ETHUSDT-25SEP2026``).
        side: ``"long"`` or ``"short"``.
        current_chain_ts: Optional chain-time upper bound. ``None`` = live mode
            (unbounded SELECT — absolute latest by ``fit_window_end_ts DESC``).
            Backtest replay MUST pass the current tick's ``chain_ts`` to prevent
            look-ahead bias from cross-run artifact accumulation. See
            ``[[fill-model-predict-look-ahead-read-path]]``.
    """
    base_sql = (
        "SELECT run_id, fit_window_start_ts, fit_window_end_ts, market_id, side, "
        "covariate_whitelist, beta, beta_stderr, "
        "log_likelihood, deviance, aic, n_observations, converged, fit_status, "
        "gof_ks_pval, gof_lr_vs_null, event_index_coverage, created_at "
        "FROM fill_model_fits "
        "WHERE market_id = ? AND side = ?"
    )
    params: tuple[object, ...] = (market_id, side)
    if current_chain_ts is not None:
        base_sql += " AND fit_window_end_ts <= ?"
        params = (market_id, side, int(current_chain_ts))
    base_sql += " ORDER BY fit_window_end_ts DESC LIMIT 1"
    with open_connection(sqlite_path) as conn:
        row = conn.execute(base_sql, params).fetchone()
    if row is None:
        return None
    return FitArtifact(
        run_id=row[0],
        fit_window_start_ts=row[1],
        fit_window_end_ts=row[2],
        market_id=row[3],
        side=row[4],
        covariate_whitelist=json.loads(row[5]),
        beta=json.loads(row[6]),
        beta_stderr=json.loads(row[7]),
        log_likelihood=row[8],
        deviance=row[9],
        aic=row[10],
        n_observations=row[11],
        converged=bool(row[12]),
        fit_status=row[13],
        gof_ks_pval=row[14],
        gof_lr_vs_null=row[15],
        event_index_coverage=row[16],
        created_at=row[17],
    )
