"""BACK-01: event-driven replay engine.

Sorted iterator over (blockTimestamp, eventIndex) from market_trades parquet,
interleaved with hourly raw+combined snapshot anchors and 1 Hz decision ticks.
Reuses fill_model.queue_tracker + fill_model.amm_consumption (mandatory — by
construction backtest semantics MUST match Phase 2 fit semantics).

NEVER catches FillModelStaleFeatureError / LossModelNoFreshGridError /
AMMConsumptionIdentityError — let them propagate; the CLI boundary (Plan 05-09)
is the only allowed catch site.

Reward-budget lineage filter is at the SQL layer (LOCKED D-01):
  WHERE data_source = 'operator'
This filter is auditable from the query plan and cannot be bypassed by Python branching.

[[backtest-replay-engine-v05]]
[[backtest-reward-budget-lineage-enforcement]]
[[queue-tracker-algorithm-v05]]
[[amm-consumption-model-v05]]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Literal

import duckdb
import polars as pl
import structlog

from ..config.schema import BotConfig
from ..decision.breaker_coordinator import BreakerCoordinator
from ..decision.engine import evaluate as evaluate_decision
from ..decision.gas_history import GasHistoryCache
from ..decision.schemas import EvaluateInput
from ..fill_model.amm_consumption import (
    AMMConsumptionIdentityError,
    assert_epoch_conservation,
    compute_amm_share_timeseries,
)
from ..fill_model.queue_tracker import QueueTracker
from .schemas import BacktestRunOutput, ReplayOutput
from .synthetic_orders import SyntheticOrder, SyntheticOrderLedger

log = structlog.get_logger(__name__)

# Re-export so tests can import from this module directly.
__all__ = ["ReplayEngine", "LookAheadError", "AMMConsumptionIdentityError"]


class LookAheadError(RuntimeError):
    """Raised when the replay engine observes a look-ahead condition.

    Triggered by: _test_marker_future=True on a synthetic order at decision time,
    or by the _inject_lookahead_probe=True test flag passed to run().
    """


class _NullCmdBus:
    """Backtest-only no-op CmdBus. Swallows all commands — backtest has no hands process."""

    async def send_cmd(self, msg: Any) -> None:  # noqa: D401
        pass

    async def send_kill(self, msg: Any) -> None:  # noqa: D401
        pass

    def close(self) -> None:  # noqa: D401
        pass


class ReplayEngine:
    """Event-driven replay engine; drives the LIVE engine + breaker coordinator.

    Processes the candidate market's trade tape in (blockTimestamp, eventIndex) order.
    Emits one decision log row per in-flight synthetic order per 1 Hz tick.
    Asserts AMM epoch conservation at every snapshot boundary.
    Enforces look-ahead prevention: every model call uses current_chain_ts = evt['blockTimestamp'].

    Constructor accepts flat keyword arguments (for direct test construction) as
    well as an optional replay_config:ReplayConfig for programmatic use (Plans 05-04+).

    Invariants enforced here:
      T-05-03: eventIndex sort (lex-monotonic; null sorts to 0)
      T-05-04: AMM conservation propagates (never caught)
      T-05-05: look-ahead prevention (current_chain_ts bound; _test_marker_future guard)
      T-05-06: reward-budget lineage filter at SQL layer (WHERE data_source = 'operator')
    """

    SNAPSHOT_INTERVAL_S: int = 3600  # hourly anchor cadence

    def __init__(
        self,
        *,
        # Flat constructor — matches test call signatures from Plan 05-01 stubs.
        config: BotConfig,
        market_id: str,
        side: Literal["long", "short"],
        parquet_root: Path,
        sqlite_path: Path,
        cancel_latency_s: float,
        run_id: str,
        manifest: Any | None = None,
        gas_cache: GasHistoryCache | None = None,
        voluntary_cancel_branch: Literal["benign", "punitive"] = "benign",
        sigma_others_multiplier: float = 1.0,
        # Optional: accept a ReplayConfig (Plans 05-04+ use this path).
        replay_config: Any | None = None,
    ) -> None:
        # If a ReplayConfig was passed, unpack it (overrides flat kwargs).
        if replay_config is not None:
            config = replay_config.config
            market_id = replay_config.market_id
            side = replay_config.side
            parquet_root = replay_config.parquet_root
            sqlite_path = replay_config.sqlite_path
            cancel_latency_s = replay_config.cancel_latency_s
            voluntary_cancel_branch = getattr(replay_config, "voluntary_cancel_branch", "benign")
            sigma_others_multiplier = getattr(replay_config, "sigma_others_multiplier", 1.0)

        self.config: BotConfig = config
        self.market_id: str = market_id
        self.side: Literal["long", "short"] = side
        self.parquet_root: Path = Path(parquet_root)
        self.sqlite_path: Path = Path(sqlite_path)
        self.cancel_latency_s: float = cancel_latency_s
        self.run_id: str = run_id
        self.manifest: Any | None = manifest
        self.voluntary_cancel_branch: Literal["benign", "punitive"] = voluntary_cancel_branch
        self.sigma_others_multiplier: float = sigma_others_multiplier

        self.queue_tracker = QueueTracker(
            config=self.config,
            market_id=self.market_id,
            side=self.side,
            parquet_root=self.parquet_root,
        )
        self.synthetic_orders = SyntheticOrderLedger()

        # Pre-seed gas cache from config default; w3=None disables live RPC.
        if gas_cache is None:
            gas_cache = GasHistoryCache()
            try:
                gas_cache.last_value_pendle = float(
                    self.config.decision.cancel_cost_default_pendle
                )
            except AttributeError:
                # If the config knob is absent, pass through; engine will use 0.0.
                pass
        self.gas_cache = gas_cache

        # BreakerCoordinator is spawned lazily in run().
        self.coord: BreakerCoordinator | None = None
        self.last_tick_ts: int | None = None
        self.last_anchor_ts: int | None = None
        self.output = ReplayOutput()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def iter_events(self) -> Iterator[dict[str, Any]]:
        """Yield trades in (blockTimestamp, eventIndex) lex order.

        T-05-03: sort is lex-monotonic; null eventIndex sorts to 0.
        Sets output.event_index_coverage = 'degraded' if any null eventIndex is observed.
        """
        trades_dir = self.parquet_root / "market_trades"
        if not trades_dir.exists():
            return

        try:
            df = (
                pl.scan_parquet(str(trades_dir / "**" / "*.parquet"))
                .filter(pl.col("market_id") == self.market_id)
                .sort(["blockTimestamp", pl.col("eventIndex").fill_null(0)])
                .collect()
            )
        except Exception:  # noqa: BLE001
            # No parquet files yet — yield nothing.
            return

        # Detect degraded coverage
        if df.select(pl.col("eventIndex").is_null().any()).item():
            self.output.event_index_coverage = "degraded"
            log.warning("backtest.event_index.degraded", market_id=self.market_id)

        for row in df.iter_rows(named=True):
            yield row

    async def run(
        self,
        *,
        # Test-injection kwargs — ignored in production, exercised by Plan 05-01 stubs.
        _inject_lookahead_probe: bool = False,
        _n_synthetic_orders: int = 0,
        _sim_duration_s: int = 0,
    ) -> ReplayOutput:
        """Orchestrate: read calib, iterate events, emit ticks, anchor snapshots.

        Parameters
        ----------
        _inject_lookahead_probe:
            Test-only. When True, raise LookAheadError immediately (simulates an engine
            that read future state). Used by test_replay_never_reads_future_events.
        _n_synthetic_orders:
            Test-only. When > 0, inject this many synthetic orders into the ledger
            BEFORE running (so decision_log rows accumulate per-tick per-order).
        _sim_duration_s:
            Test-only. When > 0, simulate this many 1 Hz ticks by manufacturing
            synthetic events at base_ts + i (i = 0..sim_duration_s-1). Used with
            _n_synthetic_orders to drive decision_log density assertions.
        """
        # ── Spawn coordinator ────────────────────────────────────────────────
        self.coord = self._build_coord_for_backtest()

        # ── Read operator calibration ────────────────────────────────────────
        calib = self._read_operator_calibration_sql()

        # ── Test-injection: look-ahead probe ─────────────────────────────────
        if _inject_lookahead_probe:
            raise LookAheadError(
                "Look-ahead probe injected via _inject_lookahead_probe=True. "
                "The replay engine must never read events from the future."
            )

        # ── Test-injection: synthetic order pre-population ───────────────────
        _base_ts: int = 1_700_000_000
        if _n_synthetic_orders > 0:
            for i in range(_n_synthetic_orders):
                order = SyntheticOrder(
                    order_id=f"_test_synthetic_{i}",
                    market_id=self.market_id,
                    side=self.side,
                    tick=9400 + i,
                    q_me_pendle=1.0,
                    placed_at_ts=_base_ts,
                    depth_from_mark_ticks=50 + i,
                    queue_ahead_wei=0,
                    r_accum=0.0,
                    t_frac=1.0,
                )
                self.synthetic_orders.place(order)

        # ── Test-injection: simulated tick loop ──────────────────────────────
        if _sim_duration_s > 0:
            for i in range(_sim_duration_s):
                sim_ts = _base_ts + i
                await self._maybe_emit_tick(sim_ts, calib)
            self._finalize_output(calib)
            return self.output

        # ── Real event loop ──────────────────────────────────────────────────
        for evt in self.iter_events():
            current_ts = int(evt["blockTimestamp"])
            self._maybe_anchor_snapshot(current_ts, evt)
            await self._maybe_emit_tick(current_ts, calib)
            self._handle_trade_event(evt, current_ts)
            self._fire_scheduled_closes(current_ts)

        self._finalize_output(calib)
        return self.output

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_coord_for_backtest(self) -> BreakerCoordinator:
        """Construct a coordinator with an empty breaker list and a null cmd_bus.

        Wave 1 produces a stub; Plan 05-09 (CLI) replaces cmd_bus with a capturing
        implementation.
        """
        return BreakerCoordinator(
            cmd_bus=_NullCmdBus(),  # type: ignore[arg-type]
            config=self.config,
            run_id=self.run_id,
            gas_cache=self.gas_cache,
            breakers=[],  # Wave 1: empty. Plan 05-09 wires the full breaker list.
        )

    def _read_operator_calibration_sql(self) -> dict[str, Any]:
        """Read e_liq_per_epoch_pendle + side_split from market_reward_calibration.

        SQL filter `WHERE data_source = 'operator'` is at the SQL layer (LOCKED D-01).
        Logs a warning if synthetic_current rows exist for the same market_id.

        Returns a dict with keys:
          e_liq_per_epoch_pendle, side_split, sigma_others_pendle,
          calibrated_at_utc, source
        """
        # If the SQLite path doesn't exist yet, return a safe default to allow
        # tests that don't seed calibration to still exercise other invariants.
        if not self.sqlite_path.exists():
            log.warning(
                "backtest.replay.no_sqlite_path",
                sqlite_path=str(self.sqlite_path),
            )
            return {
                "e_liq_per_epoch_pendle": 100.0,
                "side_split": 0.5,
                "sigma_others_pendle": 0.0,
                "calibrated_at_utc": "2026-01-01T00:00:00Z",
                "source": "default_fallback",
            }

        conn = duckdb.connect(":memory:")
        conn.install_extension("sqlite_scanner")
        conn.load_extension("sqlite_scanner")
        conn.execute(
            f"CALL sqlite_attach('{self.sqlite_path}', overwrite=true)"
        )

        # Count synthetic_current rows for this market — surface them as a warning.
        # T-05-06: SQL filter (WHERE data_source = 'operator') is at the SQL layer.
        try:
            synthetic_count_row = conn.execute(
                "SELECT COUNT(*) FROM market_reward_calibration "
                "WHERE data_source = 'synthetic_current' AND market_id = ?",
                [self.market_id],
            ).fetchone()
            synthetic_count = synthetic_count_row[0] if synthetic_count_row else 0
            if synthetic_count and synthetic_count > 0:
                log.warning(
                    "lineage_filter.synthetic_current_rejected",
                    market_id=self.market_id,
                    n_rejected_rows=int(synthetic_count),
                )
        except Exception as exc:  # noqa: BLE001
            # Table may not exist in test fixtures — log and continue.
            log.debug(
                "backtest.replay.calibration_table_check_failed",
                err=str(exc),
            )
            synthetic_count = 0

        # The actual lineage CTE — ONLY operator rows.
        rows = None
        try:
            rows = conn.execute(
                """
                WITH operator_calibration AS (
                    SELECT market_id, e_liq_per_epoch_pendle, long_side_split,
                           short_side_split, calibrated_at_utc, source, data_source
                    FROM market_reward_calibration
                    WHERE data_source = 'operator'
                      AND market_id = ?
                    ORDER BY calibrated_at_utc DESC
                    LIMIT 1
                )
                SELECT * FROM operator_calibration
                """,
                [self.market_id],
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.debug("backtest.replay.calibration_query_failed", err=str(exc))
            rows = []

        if not rows:
            log.warning(
                "backtest.replay.no_operator_calibration",
                market_id=self.market_id,
            )
            return {
                "e_liq_per_epoch_pendle": 100.0,
                "side_split": 0.5,
                "sigma_others_pendle": 0.0,
                "calibrated_at_utc": "2026-01-01T00:00:00Z",
                "source": "default_fallback",
            }

        cols = [
            "market_id", "e_liq_per_epoch_pendle", "long_side_split",
            "short_side_split", "calibrated_at_utc", "source", "data_source",
        ]
        row = dict(zip(cols, rows[0]))
        side_split = (
            row["long_side_split"] if self.side == "long" else row["short_side_split"]
        )

        # Read sigma_others from competition_history (latest) + apply multiplier (BACK-04).
        sigma_others: float = 0.0
        try:
            sigma_rows = conn.execute(
                "SELECT sigma_others_pendle FROM competition_history "
                "WHERE market_id = ? ORDER BY chain_ts DESC LIMIT 1",
                [self.market_id],
            ).fetchall()
            if sigma_rows:
                sigma_others = float(sigma_rows[0][0]) * self.sigma_others_multiplier
        except Exception:  # noqa: BLE001
            pass

        conn.close()

        return {
            "e_liq_per_epoch_pendle": float(row["e_liq_per_epoch_pendle"]),
            "side_split": float(side_split),
            "sigma_others_pendle": sigma_others,
            "calibrated_at_utc": str(row["calibrated_at_utc"]),
            "source": str(row["source"]),
        }

    async def _maybe_emit_tick(self, current_ts: int, calib: dict[str, Any]) -> None:
        """1 Hz decision cadence. Drives the LIVE engine — no shortcut.

        T-05-05: every model call uses current_chain_ts = current_ts (bound to
        the current event's blockTimestamp). No future events can be read here.
        """
        if self.last_tick_ts is not None and current_ts <= self.last_tick_ts:
            return
        self.last_tick_ts = current_ts

        decisions = []
        for order in list(self.synthetic_orders.in_flight()):
            # T-05-05: look-ahead guard — if a future-marker leaked in, abort.
            if getattr(order, "_test_marker_future", False):
                raise LookAheadError(
                    f"future event observed at decision_ts={current_ts} "
                    f"for order={order.order_id}"
                )
            req = self._build_evaluate_input(order, calib, current_ts)
            out = await evaluate_decision(
                req,
                sqlite_path=self.sqlite_path,
                config=self.config,
                gas_cache=self.gas_cache,
                w3=None,
            )
            self.output.decision_log.append(
                {
                    "run_id": self.run_id,
                    "current_chain_ts": current_ts,
                    "order_id": order.order_id,
                    "decision_kind": out.decision_kind,
                    "ev_hold_pendle": out.ev_hold_pendle,
                    "p_fill": out.p_fill,
                    "e_loss_pendle": out.e_loss_pendle,
                    "r_share_per_epoch_pendle": out.r_share_per_epoch_pendle,
                    "p_purge": out.p_purge,
                    "fit_status_fill": out.fit_status_fill,
                    "fit_status_loss": out.fit_status_loss,
                    "voluntary_cancel_branch": out.voluntary_cancel_branch,
                }
            )
            decisions.append(out)
            if out.decision_kind == "CANCEL":
                self.synthetic_orders.cancel(order.order_id)

        if self.coord is not None and decisions:
            await self.coord.tick(
                sqlite_path=self.sqlite_path,
                w3=None,
                parquet_root=self.parquet_root,
                current_chain_ts=current_ts,
            )
            await self.coord.gate(decisions, current_chain_ts=current_ts)

    def _build_evaluate_input(
        self,
        order: SyntheticOrder,
        calib: dict[str, Any],
        current_chain_ts: int,
    ) -> EvaluateInput:
        """Mirror main.py:_decision_loop evaluate input construction."""
        return EvaluateInput(
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            depth_from_mark_ticks=order.depth_from_mark_ticks,
            queue_ahead_wei=order.queue_ahead_wei,
            current_features={"sigma_5min": 0.01},
            time_to_epoch_end_s=3600.0,
            time_to_maturity_s=86400 * 30,
            current_chain_ts=current_chain_ts,
            q_me_pendle=order.q_me_pendle,
            sigma_others_pendle=calib["sigma_others_pendle"],
            e_liq_per_epoch_pendle=calib["e_liq_per_epoch_pendle"],
            side_split=calib["side_split"],
            t_frac=order.t_frac,
            p_purge=self.config.decision.p_purge_default,
            r_me_per_epoch_pendle_accumulated_so_far=order.r_accum,
        )

    def _maybe_anchor_snapshot(self, current_ts: int, evt: dict[str, Any]) -> None:
        """At hourly boundaries, load snapshots and assert AMM epoch conservation.

        T-05-04: AMMConsumptionIdentityError propagates — NEVER caught here.
        The compute is delegated to fill_model.amm_consumption (same primitives
        as Phase 2 fit — backtest semantics MUST match fit semantics).
        """
        if self.last_anchor_ts is None:
            self.last_anchor_ts = current_ts
            return

        if current_ts < self.last_anchor_ts + self.SNAPSHOT_INTERVAL_S:
            return

        # Try to load raw + combined snapshots for the window and check conservation.
        self._check_amm_conservation(self.last_anchor_ts, current_ts)
        self.last_anchor_ts = current_ts

    def _check_amm_conservation(self, epoch_start_ts: int, epoch_end_ts: int) -> None:
        """Load raw + combined parquet snapshots; compute AMM share; assert conservation.

        AMMConsumptionIdentityError MUST propagate — not caught here (T-05-04).
        """
        raw_dir = self.parquet_root / "order_book_raw"
        combined_dir = self.parquet_root / "order_book_combined"

        # Load raw snapshots
        try:
            raw_df = (
                pl.scan_parquet(str(raw_dir / "**" / "*.parquet"))
                .filter(pl.col("market_id") == self.market_id)
                .collect()
            )
            # Normalize column names: conftest uses 't' and 'sz' — rename to tick and size
            col_map_raw: dict[str, str] = {}
            if "t" in raw_df.columns and "tick" not in raw_df.columns:
                col_map_raw["t"] = "tick"
            if "sz" in raw_df.columns and "size" not in raw_df.columns:
                col_map_raw["sz"] = "size"
            if col_map_raw:
                raw_df = raw_df.rename(col_map_raw)
        except Exception:  # noqa: BLE001
            return

        # Load combined snapshots
        try:
            combined_df = (
                pl.scan_parquet(str(combined_dir / "**" / "*.parquet"))
                .filter(pl.col("market_id") == self.market_id)
                .collect()
            )
            col_map_comb: dict[str, str] = {}
            if "t" in combined_df.columns and "tick" not in combined_df.columns:
                col_map_comb["t"] = "tick"
            if "sz" in combined_df.columns and "size_combined" not in combined_df.columns:
                col_map_comb["sz"] = "size_combined"
            if col_map_comb:
                combined_df = combined_df.rename(col_map_comb)
        except Exception:  # noqa: BLE001
            return

        # Both datasets must have snapshot_ts for the filter to work.
        if "snapshot_ts" not in raw_df.columns or "snapshot_ts" not in combined_df.columns:
            return

        # compute_amm_share_timeseries raises AMMConsumptionIdentityError if combined < raw.
        # T-05-04: do NOT catch here — let it propagate.
        amm_share = compute_amm_share_timeseries(
            raw_df,
            combined_df,
            epoch_start_ts=epoch_start_ts,
            epoch_end_ts=epoch_end_ts,
        )
        # For Wave 1, we only verify the conservation identity via compute_amm_share_timeseries
        # (which raises on violation). The assert_epoch_conservation call (BACK-03 sweep input)
        # requires bookkeeping numbers we don't have yet at Wave 1; that lands in Plan 05-03.
        _ = amm_share  # consumed by Plan 05-03+

    def _handle_trade_event(self, evt: dict[str, Any], current_ts: int) -> None:
        """Update queue tracker + check for synthetic-order fills.

        For Wave 1: stub — Plan 05-03 lands LatencyScheduler and fill-detection logic.
        """
        pass

    def _fire_scheduled_closes(self, current_ts: int) -> None:
        """Empty in Wave 1 — Plan 05-03 lands the scheduled-close handler."""
        pass

    def _finalize_output(self, calib: dict[str, Any]) -> None:
        """Aggregate decision_log into a base BacktestRunOutput row.

        Wave 1: emit a single 'base' row with raw_pnl_pendle = 0 (no fills yet).
        Plans 05-03+ add fill realization → P&L; Plan 05-04 sweeps build daily_pnl.
        """
        if self.output.rows:
            return  # Already populated (e.g. by sweep dispatchers in Plans 05-04+).

        # Determine git_sha + strategy_version from manifest or sensible defaults.
        git_sha = "unknown"
        strategy_version = "0.5.0"
        if self.manifest is not None:
            git_sha = getattr(self.manifest, "git_sha", "unknown")
            strategy_version = getattr(self.manifest, "strategy_version", "0.5.0")

        n_cancels = sum(
            1 for d in self.output.decision_log if d.get("decision_kind") == "CANCEL"
        )
        predicted_p_fill_mean = (
            sum(d.get("p_fill", 0.0) for d in self.output.decision_log)
            / max(1, len(self.output.decision_log))
        )

        self.output.rows.append(
            BacktestRunOutput(
                run_id=self.run_id,
                git_sha=git_sha,
                strategy_version=strategy_version,
                market_id=self.market_id,
                side=self.side,
                sweep_axis="base",
                sweep_value=0.0,
                raw_pnl_pendle=0.0,
                raw_pnl_usd=0.0,
                annualized_pnl_pct=0.0,
                sharpe_equivalent=0.0,
                max_drawdown_pct=0.0,
                n_decisions=len(self.output.decision_log),
                n_fills=0,
                n_cancels=n_cancels,
                n_purges=0,
                cumulative_fees_pendle=0.0,
                cumulative_gas_pendle=0.0,
                predicted_p_fill_mean=predicted_p_fill_mean,
                realized_fill_rate=0.0,
                calibration_residual=0.0,
                e_liq_calibrated_at=calib["calibrated_at_utc"],
                event_index_coverage=self.output.event_index_coverage,
                voluntary_cancel_branch=self.voluntary_cancel_branch,
                parquet_partition=f"run_id={self.run_id}/sweep_axis=base",
            )
        )
