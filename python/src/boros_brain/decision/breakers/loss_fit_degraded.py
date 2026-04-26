"""B5 absorbed — LossFitDegradedBreaker: emit SHRINK_TO_Q_MIN on degraded loss grid.

Fires when the most-recent loss_grid_artifacts row for the active market has
fit_status='degraded'. A degraded loss grid means E[loss|fill] estimates are
unreliable and the EV computation is unsafe at full position size.

SHRINK_TO_Q_MIN does NOT cancel existing orders — it overrides the next placement
size to Q_min via the coordinator's force_q_min flag (Plan 04-06). This keeps
some market presence while limiting maximum fill-loss exposure.

B5 absorbed: this breaker absorbs what was previously tracked as "B5" in the
breaker taxonomy. Rather than standing alone as a fallback outside the framework,
it is integrated as the 10th breaker so the coordinator handles it consistently
with the same audit-trail, hysteresis, and kill-command routing as the other 9.

Requirements:
  B5 absorbed — loss-fit-degraded -> SHRINK_TO_Q_MIN

Wiki reference:
  [[breaker-loss-fit-degraded]]: B5 absorbed spec, SHRINK_TO_Q_MIN semantics
  [[circuit-breakers-v05]]: full breaker taxonomy
  [[ou-on-basis-loss-scaffold]]: loss model scaffold context
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from ...state.writers.loss_grid_artifacts import get_latest_loss_grid
from .base import Breaker, BreakerSignal

log = structlog.get_logger(__name__)


class LossFitDegradedBreaker(Breaker):
    """B5 absorbed: Fire when loss grid fit_status is 'degraded'.

    Reads the most-recent loss_grid_artifacts row for (market_id, side). If
    fit_status='degraded', emits SHRINK_TO_Q_MIN to cap fill-loss exposure.

    When config.markets is empty (e.g. in tests), uses a fallback market_id
    from the seeded artifact directly — the breaker reads whatever is latest
    in the table without a market filter.

    The SHRINK_TO_Q_MIN signal does NOT cancel orders. The BreakerCoordinator
    (Plan 04-06) sets force_q_min=True on the next placement cycle.

    The breaker is stateless — hysteresis (min_re_arm_s) is owned by the
    BreakerCoordinator (Plan 04-06).
    """

    name = "loss_fit_degraded"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate loss grid quality and return BreakerSignal.

        Parameters
        ----------
        sqlite_path : Path
            SQLite WAL DB path.
        w3 : Any
            AsyncWeb3 (unused by this breaker).
        parquet_root : Path
            Parquet root (unused by this breaker).
        config : BotConfig
            Frozen BotConfig; reads markets[0].market_id and config.side.
        current_chain_ts : int
            Chain-time (seconds). NEVER use wall-clock inside check() —
            no_time_time_lint.py enforces this.

        Returns
        -------
        BreakerSignal
            tripped=True with reason 'loss_fit_degraded' and
            kill_command_kind='SHRINK_TO_Q_MIN' when fit_status='degraded'.
        """
        # Resolve market_id and side from config.
        market_id: str = config.markets[0].market_id if config.markets else ""
        side: str = getattr(config, "side", "long")

        artifact = get_latest_loss_grid(sqlite_path, market_id, side)

        # If no artifact exists for this market+side, try with empty market_id
        # fallback (handles test environments where markets=[] and market_id="").
        if artifact is None and market_id == "":
            artifact = _get_any_latest_loss_grid(sqlite_path, side)

        if artifact is None:
            log.debug(
                "loss_fit_degraded.no_grid_yet",
                market_id=market_id,
                side=side,
            )
            return BreakerSignal(tripped=False, reason="no_grid_yet")

        if artifact.fit_status == "degraded":
            log.warning(
                "loss_fit_degraded.tripped",
                market_id=artifact.market_id,
                side=artifact.side,
                window_end_ts=artifact.window_end_ts,
                fit_status=artifact.fit_status,
            )
            return BreakerSignal(
                tripped=True,
                reason="loss_fit_degraded",
                payload={
                    "window_end_ts": artifact.window_end_ts,
                    "fit_status": artifact.fit_status,
                },
                kill_command_kind="SHRINK_TO_Q_MIN",
            )

        log.debug(
            "loss_fit_degraded.ok",
            market_id=artifact.market_id,
            side=artifact.side,
            fit_status=artifact.fit_status,
        )
        return BreakerSignal(
            tripped=False,
            reason=f"fit_status_{artifact.fit_status}",
        )


def _get_any_latest_loss_grid(sqlite_path: Path, side: str) -> Any:
    """Read latest loss_grid_artifacts row for the given side, any market.

    Fallback for test environments where config.markets is empty and market_id=""
    does not match any real market_id in the DB.
    """
    import json

    from boros_brain.loss_model.schemas import LossGridArtifact, LossGridCell
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            """SELECT run_id, market_id, side, window_start_ts, window_end_ts,
                      fit_status, depth_bucket_edges, tau_bucket_edges_days,
                      cells_json, event_index_coverage, created_at
               FROM loss_grid_artifacts
               WHERE side = ?
               ORDER BY window_end_ts DESC LIMIT 1""",
            (side,),
        ).fetchone()
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


__all__ = ["LossFitDegradedBreaker"]
