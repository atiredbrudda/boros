"""SAFE-08 — SideBudgetBreaker: per-side reward budget drift > drift_threshold in 1 epoch.

Detects when the long/short reward budget split has drifted significantly since
the operator's last calibration. A 30%+ drift means the side-split assumption
is stale and placement should be paused for recalibration.

drift_pct = (lag_split - latest_split) / lag_split

Pitfall #3 first-day operator-pause noise guard: len(rows) < 2 → returns
reason='insufficient_calibration_history' without firing.

T-04-05-03: calibrated_at_utc is ISO8601; Z → +00:00 substitution handles
both Pendle docs format ("2026-04-25T00:00:00Z") and Python datetime
("2026-04-25T00:00:00+00:00").

[[breaker-side-budget-rebalance]]: SAFE-08 spec, drift_threshold, A2 absorbed
[[circuit-breakers-v05]]: breaker taxonomy + routing
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import Breaker, BreakerSignal
from ...state.writers.market_reward_calibration import read_market_reward_calibration_history

__all__ = ["SideBudgetBreaker"]


class SideBudgetBreaker(Breaker):
    """SAFE-08: fires when the side-budget split drifts > drift_threshold in 1 epoch.

    Compares the latest calibration row vs the row approximately 1 epoch older.
    The breaker uses the side from config.side to select long_side_split or
    short_side_split for the comparison.

    Pitfall #3 guard: if fewer than 2 calibration rows exist, the breaker
    stays silent with reason='insufficient_calibration_history'.
    """

    name = "side_budget"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate SAFE-08 side budget drift condition."""
        cfg = config.decision.breakers.side_budget
        market = config.markets[0]

        rows = read_market_reward_calibration_history(sqlite_path, market.market_id, limit=10)

        # Pitfall #3 first-day operator-pause noise guard.
        if len(rows) < 2:
            return BreakerSignal(
                tripped=False,
                reason="insufficient_calibration_history",
                payload={"n": len(rows)},
            )

        # rows ordered DESC by calibrated_at_utc; row[0] = latest, row[-1] = oldest.
        latest = rows[0]

        # Find the row approximately 1 epoch older than latest.
        # T-04-05-03: normalize Z → +00:00 for fromisoformat compatibility.
        latest_ts_str = latest["calibrated_at_utc"].replace("Z", "+00:00")
        latest_dt = datetime.fromisoformat(latest_ts_str)
        one_epoch_iso = (
            latest_dt - timedelta(days=config.reward_share_model.epoch_days)
        ).isoformat()

        epoch_lag_row = next(
            (r for r in rows if r["calibrated_at_utc"].replace("Z", "+00:00") <= one_epoch_iso),
            rows[-1],  # fall back to oldest available row
        )

        # Select the split field based on config.side.
        if config.side == "long":
            latest_split = latest["long_side_split"]
            lag_split = epoch_lag_row["long_side_split"]
        else:
            latest_split = latest["short_side_split"]
            lag_split = epoch_lag_row["short_side_split"]

        if lag_split <= 0:
            return BreakerSignal(tripped=False, reason="zero_baseline_split")

        drift_pct = (lag_split - latest_split) / lag_split

        if drift_pct > cfg.drift_threshold:
            return BreakerSignal(
                tripped=True,
                reason="side_budget_rebalance",
                payload={
                    "drift_pct": drift_pct,
                    "latest_split": latest_split,
                    "lag_split": lag_split,
                },
                kill_command_kind="HALVE_POSITION_AND_ALERT",
            )

        return BreakerSignal(
            tripped=False,
            reason="ok",
            payload={"drift_pct": drift_pct},
        )
