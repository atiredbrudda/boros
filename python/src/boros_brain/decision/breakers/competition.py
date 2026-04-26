"""SAFE-06 — CompetitionBreaker: Q_total_in_range drop > drop_threshold in 1 epoch.

Detects sudden collapse in competing order flow. If Q_total (q_me + sigma_others)
drops by more than drop_threshold (default 50%) over one epoch window, the CLO
range may be about to shift dramatically or the market is becoming illiquid.

Pitfall #3 first-day operator-pause noise guard: len(rows) < 2 → returns
reason='insufficient_history' without firing. At least 2 data points are
required to compute an epoch-lag comparison.

STRIDE: T-04-05-01 — first-day guard prevents false-fire on day 1.

[[breaker-competition-collapse]]: SAFE-06 spec, drop_threshold default, Pitfall #3
[[circuit-breakers-v05]]: breaker taxonomy + routing
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...state.writers.competition_history import read_competition_history_since
from .base import Breaker, BreakerSignal

__all__ = ["CompetitionBreaker"]


class CompetitionBreaker(Breaker):
    """SAFE-06: fires when Q_total_in_range drops > drop_threshold in 1 epoch.

    Q_total = q_me_pendle + sigma_others_pendle per competition_history row.
    The breaker compares the oldest row in the epoch window (lag) vs the newest
    (current). Both rows must exist — first-day guard (Pitfall #3) returns
    reason='insufficient_history' if fewer than 2 rows are available.
    """

    name = "competition"

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate SAFE-06 competition collapse condition."""
        cfg = config.decision.breakers.competition
        market = config.markets[0]
        one_epoch_ago = current_chain_ts - int(config.reward_share_model.epoch_days * 86400)

        rows = read_competition_history_since(sqlite_path, market.market_id, one_epoch_ago)

        # Pitfall #3 first-day operator-pause noise guard.
        if len(rows) < 2:
            return BreakerSignal(
                tripped=False,
                reason="insufficient_history",
                payload={"n": len(rows)},
            )

        # Q_total = q_me + sigma_others per row; rows ordered ASC by chain_ts.
        q_total_lag = rows[0]["q_me_pendle"] + rows[0]["sigma_others_pendle"]
        q_total_now = rows[-1]["q_me_pendle"] + rows[-1]["sigma_others_pendle"]

        if q_total_lag <= 0:
            return BreakerSignal(tripped=False, reason="zero_baseline")

        drop_pct = (q_total_lag - q_total_now) / q_total_lag

        if drop_pct > cfg.drop_threshold:
            return BreakerSignal(
                tripped=True,
                reason="competition_collapse",
                payload={
                    "drop_pct": drop_pct,
                    "q_total_now": q_total_now,
                    "q_total_lag": q_total_lag,
                },
                kill_command_kind="PAUSE_AND_ALERT",
            )

        return BreakerSignal(
            tripped=False,
            reason="ok",
            payload={"drop_pct": drop_pct},
        )
