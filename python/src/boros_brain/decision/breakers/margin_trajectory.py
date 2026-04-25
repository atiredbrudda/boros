"""SAFE-01 — MarginTrajectoryBreaker: sliding-window linear regression on net margin.

Fires when a linear regression on the recent margin_history predicts that net margin
will breach the maintenance margin floor within time_to_mm_threshold_s seconds.

Pitfall #4 sign-confusion guard: slope < 0 means net margin is SHRINKING (bad).
Positive slope means net margin is GROWING (healthy). The breaker NEVER fires when
slope >= 0 — this is the Pitfall #4 guard.

Requirements:
  SAFE-01 — margin trajectory predictive circuit breaker

Wiki reference:
  [[breaker-margin-trajectory]]: spec, knobs, Pitfall #4 guard detail
  [[circuit-breakers-v05]]: full breaker taxonomy

Strategy non-negotiable:
  EV-based cancel rule per CLAUDE.md. This breaker fires an EMERGENCY_CLOSE
  (liquidation avoidance) when the extrapolated time-to-maintenance-margin
  is below time_to_mm_threshold_s.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import structlog

from .base import Breaker, BreakerSignal
from ...state.writers.margin_history import read_margin_history

log = structlog.get_logger(__name__)


class MarginTrajectoryBreaker(Breaker):
    """SAFE-01: Predict margin breach via linear regression on recent margin_history.

    Reads margin_history rows within the last `window_s` seconds and fits a
    linear trend (np.polyfit). If the trend is negative (margin shrinking) and
    the extrapolated time to maintenance margin is below `time_to_mm_threshold_s`,
    fires EMERGENCY_CLOSE.

    Pitfall #4 sign-confusion: slope < 0 means margin is SHRINKING (fire candidate).
    Positive slope = healthy growth = NO fire. The `if slope >= 0` guard is the
    canonical test for this pitfall.

    The breaker is stateless — hysteresis (min_re_arm_s) is owned by the
    BreakerCoordinator (Plan 04-06).
    """

    name = "margin_trajectory"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate margin trajectory and return BreakerSignal.

        Parameters
        ----------
        sqlite_path : Path
            SQLite WAL DB path.
        w3 : Any
            AsyncWeb3 (unused by this breaker — fIndex not needed for margin).
        parquet_root : Path
            Parquet root (unused by this breaker).
        config : BotConfig
            Frozen BotConfig; reads decision.breakers.margin and markets list.
        current_chain_ts : int
            Chain-time (seconds). NEVER use wall-clock inside check() —
            no_time_time_lint.py enforces this.

        Returns
        -------
        BreakerSignal
            tripped=True with reason 'margin_trajectory_predicted_breach' and
            kill_command_kind='EMERGENCY_CLOSE' when a breach is predicted.
        """
        cfg = config.decision.breakers.margin
        market_id = config.markets[0].market_id if config.markets else None

        since_ts = current_chain_ts - int(cfg.window_s)
        rows = read_margin_history(
            sqlite_path,
            market_id=market_id,
            since_ts=since_ts,
        )

        if len(rows) < cfg.min_samples:
            log.debug(
                "margin_trajectory.insufficient_history",
                n=len(rows),
                min_samples=cfg.min_samples,
            )
            return BreakerSignal(
                tripped=False,
                reason="insufficient_history",
                payload={"n": len(rows), "min_samples": cfg.min_samples},
            )

        ts = np.array([r["chain_ts"] for r in rows], dtype=float)
        nm = np.array([r["net_margin_usd"] for r in rows], dtype=float)
        mm = float(rows[-1]["maintenance_margin_usd"])

        # np.polyfit returns (slope, intercept) for degree=1.
        # Pitfall #4: slope >= 0 means margin is GROWING (healthy) → NO fire.
        # Only a negative slope (margin shrinking) is a fire candidate.
        slope, intercept = np.polyfit(ts, nm, 1)

        if slope >= 0:
            log.debug(
                "margin_trajectory.growing",
                slope_usd_per_s=float(slope),
            )
            return BreakerSignal(
                tripped=False,
                reason="growing",
                payload={"slope_usd_per_s": float(slope)},
            )

        # Extrapolate: nm(t) = slope * t + intercept → solve for nm = mm.
        # t* = (mm - intercept) / slope  (negative denominator → t* in future when slope < 0)
        t_star = (mm - intercept) / slope
        t_to_mm = t_star - current_chain_ts

        if t_to_mm < cfg.time_to_mm_threshold_s:
            log.warning(
                "margin_trajectory.breach_predicted",
                slope_usd_per_s=float(slope),
                t_to_mm_s=float(t_to_mm),
                mm_floor_usd=mm,
                threshold_s=cfg.time_to_mm_threshold_s,
            )
            return BreakerSignal(
                tripped=True,
                reason="margin_trajectory_predicted_breach",
                payload={
                    "slope_usd_per_s": float(slope),
                    "t_to_mm_s": float(t_to_mm),
                    "mm_floor_usd": mm,
                },
                kill_command_kind="EMERGENCY_CLOSE",
            )

        log.debug(
            "margin_trajectory.ok",
            slope_usd_per_s=float(slope),
            t_to_mm_s=float(t_to_mm),
        )
        return BreakerSignal(
            tripped=False,
            reason="ok",
            payload={"slope_usd_per_s": float(slope), "t_to_mm_s": float(t_to_mm)},
        )


__all__ = ["MarginTrajectoryBreaker"]
