"""FILL-03: queue-position tracker with tri-track replay + drift diagnostic.

Replays the `market-trades` parquet tape (eventIndex-ordered) between hourly
`order_book_raw/` anchors, maintaining per-tick queue-ahead-of-us estimates in
three parallel tracks:
  - pessimistic: every invisible event treated as a new placement ahead of us
  - realized:    only visible market-trades consume the book
  - optimistic:  every invisible event treated as a cancel ahead of us

By construction (PITFALLS §B1): pessimistic >= realized >= optimistic at every
tick. The decision engine consumes the pessimistic bound via
`config.fill_model.queue_tracker_bias_mode = "pessimistic"` (default).

Drift is the diagnostic — widening bracket means more invisible-event activity.
NOT a failure — emit log events, let operator investigate.

[[queue-tracker-algorithm-v05]]
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import polars as pl
import structlog

from ..config.schema import BotConfig
from .schemas import ReplayResult

log = structlog.get_logger(__name__)

__all__ = ["QueueTracker", "compute_drift_diagnostic"]


def compute_drift_diagnostic(
    replay_queue: dict[int, float],
    snapshot_queue: dict[int, float],
) -> dict[str, float]:
    """Signed drift per tick: replay_predicted - snapshot_observed.

    Positive mean => replay over-estimates queue (conservative fill prediction).
    Negative mean => replay under-estimates (liberal). Both are information;
    neither is failure.

    Returns dict with keys: drift_signed_mean, drift_magnitude_mean,
    drift_std, n_ticks_compared.
    """
    ticks = set(replay_queue) | set(snapshot_queue)
    if not ticks:
        return {
            "drift_signed_mean": 0.0,
            "drift_magnitude_mean": 0.0,
            "drift_std": 0.0,
            "n_ticks_compared": 0.0,
        }
    drifts = np.array(
        [replay_queue.get(t, 0.0) - snapshot_queue.get(t, 0.0) for t in ticks],
        dtype=float,
    )
    return {
        "drift_signed_mean": float(drifts.mean()),
        "drift_magnitude_mean": float(np.abs(drifts).mean()),
        "drift_std": float(drifts.std(ddof=1)) if len(drifts) > 1 else 0.0,
        "n_ticks_compared": float(len(ticks)),
    }


class QueueTracker:
    """Tri-track replay per (market_id, side).

    Usage:
        tracker = QueueTracker(config=bot_config, market_id="BINANCE-ETHUSDT-29MAY2026", side="long")
        result = tracker.replay_window(window_start_ts=..., window_end_ts=...)
        # result: ReplayResult with per-tick queue sizes at each hourly anchor + drift diagnostics
    """

    def __init__(self, config: BotConfig, market_id: str, side: Literal["long", "short"]) -> None:
        self.config = config
        self.market_id = market_id
        self.side = side

    # ------------------------------------------------------------------
    # Internal replay helpers
    # ------------------------------------------------------------------

    def _load_trades(self, window_start_ts: int, window_end_ts: int) -> tuple[pl.DataFrame, str]:
        """Load + sort tape. Returns (sorted_df, event_index_coverage)."""
        trades = pl.scan_parquet("data/parquet/market_trades/**/*.parquet").filter(
            (pl.col("blockTimestamp") >= window_start_ts)
            & (pl.col("blockTimestamp") < window_end_ts)
            & (pl.col("market_id") == self.market_id)
            & (pl.col("side") == self.side)
        ).collect()

        coverage: str = "full"
        if trades.is_empty():
            return trades, coverage

        null_count = int(trades["eventIndex"].null_count())
        if null_count > 0:
            log.warning(
                "fill_model.eventindex_coverage_degraded",
                market_id=self.market_id,
                side=self.side,
                null_rows=null_count,
                total_rows=trades.height,
            )
            coverage = "degraded"
            trades = trades.with_columns(pl.col("eventIndex").fill_null(0))
        trades = trades.sort(["blockTimestamp", "eventIndex"])
        return trades, coverage

    def _load_raw_snapshots(self, window_start_ts: int, window_end_ts: int) -> pl.DataFrame:
        return pl.scan_parquet("data/parquet/order_book_raw/**/*.parquet").filter(
            (pl.col("snapshot_ts") >= window_start_ts)
            & (pl.col("snapshot_ts") < window_end_ts)
            & (pl.col("market_id") == self.market_id)
            & (pl.col("side") == self.side)
        ).collect()

    def _snapshot_queue_at(self, raw: pl.DataFrame, anchor_ts: int) -> dict[int, float]:
        """Tick -> queue size at a given snapshot_ts."""
        rows = raw.filter(pl.col("snapshot_ts") == anchor_ts).select(["tick", "size"]).to_dicts()
        return {int(r["tick"]): float(r["size"]) for r in rows}

    def _replay_realized(
        self,
        start_queue: dict[int, float],
        trades_in_interval: pl.DataFrame,
    ) -> dict[int, float]:
        """Decrement queue by visible takers only."""
        queue = dict(start_queue)
        for row in trades_in_interval.iter_rows(named=True):
            tick = int(row["tick"]) if "tick" in row else 0
            consumed = float(row["size"]) if "size" in row else 0.0
            queue[tick] = max(queue.get(tick, 0.0) - consumed, 0.0)
        return queue

    def _replay_pessimistic(
        self,
        start_queue: dict[int, float],
        trades_in_interval: pl.DataFrame,
        snapshot_next_queue: dict[int, float],
    ) -> dict[int, float]:
        """Invisible events = placements ahead. Take realized replay's result and
        bump UP to snapshot_next at any tick where snapshot_next > realized."""
        realized = self._replay_realized(start_queue, trades_in_interval)
        pessimistic = dict(realized)
        for tick, snap_size in snapshot_next_queue.items():
            if snap_size > realized.get(tick, 0.0):
                pessimistic[tick] = snap_size
        return pessimistic

    def _replay_optimistic(
        self,
        start_queue: dict[int, float],
        trades_in_interval: pl.DataFrame,
        snapshot_next_queue: dict[int, float],
    ) -> dict[int, float]:
        """Invisible events = cancels ahead. Take realized and cap DOWN at snapshot_next."""
        realized = self._replay_realized(start_queue, trades_in_interval)
        optimistic = dict(realized)
        for tick in realized:
            if snapshot_next_queue.get(tick, 0.0) < optimistic[tick]:
                optimistic[tick] = snapshot_next_queue.get(tick, 0.0)
        return optimistic

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def replay_window(self, window_start_ts: int, window_end_ts: int) -> ReplayResult:
        """Replay the trade tape and compute tri-track queue estimates.

        Returns a ReplayResult with per-anchor queue dicts + per-hour drift
        diagnostics + event_index_coverage flag.
        """
        trades, coverage = self._load_trades(window_start_ts, window_end_ts)
        raw = self._load_raw_snapshots(window_start_ts, window_end_ts)

        if raw.is_empty():
            return ReplayResult(
                market_id=self.market_id,
                side=self.side,
                window_start_ts=window_start_ts,
                window_end_ts=window_end_ts,
                event_index_coverage=coverage,  # type: ignore[arg-type]
            )

        anchors = sorted({int(t) for t in raw["snapshot_ts"].unique().to_list()})

        pess: dict[int, dict[int, float]] = {}
        real: dict[int, dict[int, float]] = {}
        opt: dict[int, dict[int, float]] = {}
        diags: list[dict[str, float]] = []

        # For each adjacent pair (anchor_i, anchor_{i+1}), run three replays.
        for i, anchor_ts in enumerate(anchors[:-1]):
            next_ts = anchors[i + 1]
            snap_now = self._snapshot_queue_at(raw, anchor_ts)
            snap_next = self._snapshot_queue_at(raw, next_ts)
            trades_iv = trades.filter(
                (pl.col("blockTimestamp") >= anchor_ts) & (pl.col("blockTimestamp") < next_ts)
            )

            real[next_ts] = self._replay_realized(snap_now, trades_iv)
            pess[next_ts] = self._replay_pessimistic(snap_now, trades_iv, snap_next)
            opt[next_ts] = self._replay_optimistic(snap_now, trades_iv, snap_next)

            # Drift diagnostic: replay_predicted (realized) vs actual snapshot at next_ts
            diag = compute_drift_diagnostic(replay_queue=real[next_ts], snapshot_queue=snap_next)
            log.info(
                "fill_model.queue_drift_reconciliation",
                market_id=self.market_id,
                side=self.side,
                anchor_ts=anchor_ts,
                next_ts=next_ts,
                drift_signed_mean=diag["drift_signed_mean"],
                drift_magnitude_mean=diag["drift_magnitude_mean"],
                drift_std=diag["drift_std"],
                n_ticks_compared=int(diag["n_ticks_compared"]),
            )
            diags.append(diag)

            # Bracket-width warn: if max(pess - opt) > multiplier * hourly_mean_queue
            ticks = set(pess[next_ts]) | set(opt[next_ts])
            if ticks:
                widths = [pess[next_ts].get(t, 0.0) - opt[next_ts].get(t, 0.0) for t in ticks]
                mean_queue = float(np.mean([real[next_ts].get(t, 0.0) for t in ticks]) or 1.0)
                max_width = float(max(widths))
                multiplier = self.config.fill_model.bracket_width_warn_multiplier
                if mean_queue > 0.0 and max_width > multiplier * mean_queue:
                    log.warning(
                        "fill_model.bracket_width_warn",
                        market_id=self.market_id,
                        side=self.side,
                        anchor_ts=anchor_ts,
                        next_ts=next_ts,
                        bracket_width=max_width,
                        hourly_mean_queue=mean_queue,
                        multiplier=multiplier,
                    )

        return ReplayResult(
            market_id=self.market_id,
            side=self.side,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
            pessimistic_queue_at_anchor=pess,
            realized_queue_at_anchor=real,
            optimistic_queue_at_anchor=opt,
            drift_diagnostics_per_hour=diags,
            event_index_coverage=coverage,  # type: ignore[arg-type]
        )
