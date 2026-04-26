"""LOSS-02 sync expected_loss() contract. Phase 4 DecisionEngine + Plan 03-03 Sizer
call this at 1 Hz.

Contract:
    - SYNC (not async). p95 < 10ms budget.
    - Sparse-cell fallback: exact -> nearest_neighbor -> coarse_bound (warn log each).
    - NEVER silently returns 0; coarse_bound uses config.screener.fill_loss_coarse_bound.
    - Grid older than fit_max_staleness_s -> LossModelNoFreshGridError.
    - Unit: PENDLE (matches R_capped in the EV equation).

Design-locked. Any change to this signature is a Phase-4 breaking change.

T-03-03 / T-03-04 mitigations: explicit n_samples == 0 branch routes to
coarse_bound; every fallback emits ``loss_model.sparse_cell_fallback`` so the
operator can audit grid sparsity.
"""

from __future__ import annotations

import math
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..state.writers.loss_grid_artifacts import get_latest_loss_grid
from .config import LossModelConfig
from .schemas import (
    ExpectedLossInput,
    ExpectedLossOutput,
    LossGridArtifact,
    LossGridCell,
    LossModelNoFreshGridError,
)


def _get_loss_model_config(config: BotConfig) -> LossModelConfig:
    """Plan-03-01-independent fallback. Mirror of replay._get_loss_model_config."""
    return getattr(config, "loss_model", None) or LossModelConfig()


log = structlog.get_logger(__name__)

__all__ = [
    "expected_loss",
    "ExpectedLossInput",
    "ExpectedLossOutput",
    "LossModelNoFreshGridError",
]


def _bucket_idx(value: float, edges: list[float]) -> int:
    """Same convention as fit._bucket_idx — duplicated here to keep loss_model
    sync-path free of cross-module imports for the 1 Hz hot path."""
    n = len(edges)
    if n < 2:
        return 0
    if value <= edges[0]:
        return 0
    for i in range(n - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    return n - 2


def _select_metric(cell: LossGridCell, aggregation_metric: str) -> float:
    """Map aggregation_metric knob to the cell field."""
    if aggregation_metric == "p50":
        return cell.p50_pendle
    if aggregation_metric == "p95":
        return cell.p95_pendle
    return cell.mean_pendle


def expected_loss(
    req: ExpectedLossInput,
    *,
    sqlite_path: Path,
    config: BotConfig,
) -> ExpectedLossOutput:
    """Sync expected_loss. See module docstring for contract.

    Raises:
        LossModelNoFreshGridError: no grid persisted OR grid age > fit_max_staleness_s.
        ValueError: req.time_to_maturity_s < 0 (Phase 4 SAFE-07 already breaks earlier).
    """
    if req.time_to_maturity_s < 0:
        raise ValueError(f"negative tau: {req.time_to_maturity_s}")

    artifact: LossGridArtifact | None = get_latest_loss_grid(sqlite_path, req.market_id, req.side)
    if artifact is None:
        log.warning(
            "loss_model.no_fresh_grid",
            market_id=req.market_id,
            side=req.side,
            reason="no_grid_row",
        )
        raise LossModelNoFreshGridError(f"no grid for ({req.market_id}, {req.side})")

    grid_age_s = float(req.current_chain_ts - artifact.window_end_ts)
    if grid_age_s < 0:
        # Future-dated artifact (clock skew) — treat as fresh, log warning.
        log.warning(
            "loss_model.future_dated_grid",
            market_id=req.market_id,
            side=req.side,
            window_end_ts=artifact.window_end_ts,
            current_chain_ts=req.current_chain_ts,
            grid_age_s=grid_age_s,
        )
        grid_age_s = 0.0

    if grid_age_s > _get_loss_model_config(config).fit_max_staleness_s:
        log.warning(
            "loss_model.no_fresh_grid",
            market_id=req.market_id,
            side=req.side,
            grid_age_s=grid_age_s,
            fit_max_staleness_s=_get_loss_model_config(config).fit_max_staleness_s,
        )
        raise LossModelNoFreshGridError(
            f"grid too stale: age={grid_age_s}s > " f"max={_get_loss_model_config(config).fit_max_staleness_s}s"
        )

    final_status = artifact.fit_status
    if grid_age_s > _get_loss_model_config(config).fit_warn_staleness_s and final_status == "ok":
        final_status = "stale"
        log.warning(
            "loss_model.expected_loss_stale_grid",
            market_id=req.market_id,
            side=req.side,
            grid_age_s=grid_age_s,
        )

    # Compute target (depth_bucket_idx, tau_bucket_idx).
    depth_clamped = max(0, int(req.depth_from_mark_ticks))
    tau_days = float(req.time_to_maturity_s) / 86400.0
    d_idx = _bucket_idx(float(depth_clamped), artifact.depth_bucket_edges)
    t_idx = _bucket_idx(tau_days, artifact.tau_bucket_edges_days)

    # Exact-cell lookup
    target_cell: LossGridCell | None = None
    for c in artifact.cells:
        if c.depth_bucket_idx == d_idx and c.tau_bucket_idx == t_idx:
            target_cell = c
            break

    min_samp = _get_loss_model_config(config).min_samples_per_cell
    agg = _get_loss_model_config(config).aggregation_metric

    if target_cell is not None and target_cell.n_samples >= min_samp:
        value = _select_metric(target_cell, agg)
        return ExpectedLossOutput(
            expected_loss_pendle=float(value),
            cell_n_samples=int(target_cell.n_samples),
            cell_p50_pendle=float(target_cell.p50_pendle),
            cell_p95_pendle=float(target_cell.p95_pendle),
            fallback_mode="exact",
            grid_artifact_run_id=artifact.run_id,
            grid_age_s=grid_age_s,
            fit_status=final_status,  # type: ignore[arg-type]
        )

    # k-NN: top-knn_k neighbors within knn_max_distance, weighted by n_samples.
    knn_k = _get_loss_model_config(config).knn_k
    knn_max = _get_loss_model_config(config).knn_max_distance

    # Compute distances to all populated cells.
    neighbors: list[tuple[float, LossGridCell]] = []
    for c in artifact.cells:
        if c.n_samples == 0:
            continue
        dist = math.sqrt((c.depth_bucket_idx - d_idx) ** 2 + (c.tau_bucket_idx - t_idx) ** 2)
        if dist <= knn_max:
            neighbors.append((dist, c))
    neighbors.sort(key=lambda x: x[0])
    top_k = neighbors[:knn_k]
    total_n = sum(c.n_samples for _, c in top_k)

    if top_k and total_n >= min_samp:
        # Weighted aggregation by n_samples.
        weighted = sum(_select_metric(c, agg) * c.n_samples for _, c in top_k) / total_n
        # Use weighted means for p50/p95 surfacing too — operator inspects the cell
        # distribution from the weighted summary.
        weighted_p50 = sum(c.p50_pendle * c.n_samples for _, c in top_k) / total_n
        weighted_p95 = sum(c.p95_pendle * c.n_samples for _, c in top_k) / total_n

        log.warning(
            "loss_model.sparse_cell_fallback",
            market_id=req.market_id,
            side=req.side,
            depth=req.depth_from_mark_ticks,
            tau_days=tau_days,
            fallback_mode="nearest_neighbor",
            n_neighbors=len(top_k),
            total_n_samples=total_n,
            grid_age_s=grid_age_s,
        )

        return ExpectedLossOutput(
            expected_loss_pendle=float(weighted),
            cell_n_samples=int(total_n),
            cell_p50_pendle=float(weighted_p50),
            cell_p95_pendle=float(weighted_p95),
            fallback_mode="nearest_neighbor",
            grid_artifact_run_id=artifact.run_id,
            grid_age_s=grid_age_s,
            fit_status=final_status,  # type: ignore[arg-type]
        )

    # Coarse_bound: fill_loss_coarse_bound × notional_proxy (1 PENDLE for v0.5).
    coarse = float(config.screener.fill_loss_coarse_bound) * 1.0
    log.warning(
        "loss_model.sparse_cell_fallback",
        market_id=req.market_id,
        side=req.side,
        depth=req.depth_from_mark_ticks,
        tau_days=tau_days,
        fallback_mode="coarse_bound",
        coarse_bound=config.screener.fill_loss_coarse_bound,
        grid_age_s=grid_age_s,
    )
    return ExpectedLossOutput(
        expected_loss_pendle=coarse,
        cell_n_samples=0,
        cell_p50_pendle=coarse,
        cell_p95_pendle=coarse * 2.0,
        fallback_mode="coarse_bound",
        grid_artifact_run_id=artifact.run_id,
        grid_age_s=grid_age_s,
        fit_status=final_status,  # type: ignore[arg-type]
    )
