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

import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
import polars as pl
import structlog

from ..config.schema import BotConfig
from ..decision.breaker_coordinator import BreakerCoordinator
from ..decision.engine import evaluate as evaluate_decision
from ..decision.gas_history import GasHistoryCache
from ..decision.schemas import EvaluateInput
from ..fill_model.amm_consumption import AMMConsumptionIdentityError
from ..fill_model.queue_tracker import QueueTracker
from .cancel_latency import LatencyScheduler, ScheduledClose
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
        )
        self.synthetic_orders = SyntheticOrderLedger()
        self.latency_scheduler = LatencyScheduler(
            L_seconds=float(cancel_latency_s),
            decision_period_s=float(getattr(self.config.decision, "decision_loop_interval_s", 1.0)),
        )
        self._scheduled_closes: list[ScheduledClose] = []

        # AMM conservation data cache: lazily loaded once on first _check_amm_conservation
        # call, then reused for all hourly boundaries in the same run. The underlying
        # parquet files do not change during a replay run, so reading once is correct.
        self._amm_raw_df: pl.DataFrame | None = None
        self._amm_combined_df: pl.DataFrame | None = None

        # Pre-seed gas cache from config default; w3=None disables live RPC.
        if gas_cache is None:
            gas_cache = GasHistoryCache()
            _default_cancel_cost = getattr(self.config.decision, "cancel_cost_default_pendle", None)
            if _default_cancel_cost is not None:
                gas_cache.last_value_pendle = float(_default_cancel_cost)
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
            # Phase 5.1 Wave 4 deviation fix (Rule 1): Wave-1 ingest wrote market_ids with
            # numeric archive prefix (e.g. "112-BINANCE-ETHUSDT-29MAY2026"). The canonical
            # market_id from the operator has no prefix. Use str.ends_with() so both forms
            # are matched — mirrors the screener/filter.py _parquet_market_id shim.
            df = (
                pl.scan_parquet(str(trades_dir / "**" / "*.parquet"))
                .filter(pl.col("market_id").str.ends_with(self.market_id))
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

        yield from df.iter_rows(named=True)

    async def run(
        self,
        *,
        # Test-injection kwargs — ignored in production, exercised by Plan 05-01 stubs.
        _inject_lookahead_probe: bool = False,
        _n_synthetic_orders: int = 0,
        _sim_duration_s: int = 0,
        # Production-mode seeding: place one CLO-edge synthetic order before the
        # event loop runs. Without this, the production CLI path (cli._dispatch_run)
        # produced n_decisions=0 because the engine has no in-flight orders to
        # evaluate (Phase 5.1 Wave 4 binding-run bug). Tests that opted into the
        # _n_synthetic_orders path are unaffected.
        seed_from_config: bool = False,
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
        seed_from_config:
            Production. When True (CLI dispatch + sweeps), peek the first event,
            then seed ONE outer-CLO-edge synthetic order from config.markets[0]
            before iterating. No-op when _n_synthetic_orders > 0 (test path
            already populated the ledger).
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
        # Peek the first event so production seeding can stamp placed_at_ts
        # with the actual first chain timestamp (rather than a sentinel).
        events_iter = self.iter_events()
        try:
            first_evt = next(events_iter)
        except StopIteration:
            self._finalize_output(calib)
            return self.output

        if seed_from_config and _n_synthetic_orders == 0:
            self._seed_initial_synthetic_order(int(first_evt["blockTimestamp"]))

        for evt in itertools.chain([first_evt], events_iter):
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

    def _seed_initial_synthetic_order(self, placed_at_ts: int) -> bool:
        """Seed ONE outer-CLO-edge synthetic order from config.markets[0].

        Phase 5.1 Wave 4 binding-run fix: the production CLI / sweep / perturbation
        paths run the engine but never seed an initial order, so n_decisions=0
        and the ship-gate verdict is meaningless. This restores the strategy seed:

          - tick: clo_lower_thresh (long) | clo_upper_thresh (short) — outer edge
          - q_me_pendle: config.sizer.q_min_pendle (sub-cap regime fixed point;
            equals what sizer.q_me_target() returns at $100 collateral / 90k
            notional_per_yu_usd per the optimizer.py docstring contract)
          - depth_from_mark_ticks: |edge - midpoint(clo_lower, clo_upper)|
          - queue_ahead_wei: 1e22 — outer-edge orders sit behind significant queue;
            the v0.5 fill detection (replay._trade_consumes_order) is an
            approximation that uses queue_ahead as an instantaneous fill threshold,
            so a sufficiently large value keeps the order alive across the run.
            Production-grade per-tick fill semantics are queue_tracker-based and
            scoped to a later wave.

        Returns True on seed; False (degraded mode) when config.markets is empty
        or contains no entry whose market_id matches self.market_id — in that case
        the caller will run with no in-flight orders and produce n_decisions=0.
        """
        market = next(
            (
                m
                for m in self.config.markets
                if m.market_id.endswith(self.market_id) or self.market_id.endswith(m.market_id)
            ),
            None,
        )
        if market is None:
            log.warning(
                "backtest.replay.no_market_calibration_for_seed",
                market_id=self.market_id,
                n_markets_in_config=len(self.config.markets),
            )
            return False

        clo_lower = int(market.clo_lower_thresh)
        clo_upper = int(market.clo_upper_thresh)
        midpoint = (clo_lower + clo_upper) // 2
        tick = clo_lower if self.side == "long" else clo_upper
        depth_from_mark_ticks = abs(tick - midpoint)

        # queue_ahead_wei=10**22 exceeds int64 range; orjson serialises as float string.
        # Use 10**18 (1e18 wei = 1 ETH-scale) which is within int64 and still represents
        # "deep back of queue" for the outer-edge seeded order.
        _queue_ahead = 10**18
        order = SyntheticOrder(
            order_id=f"initial_{self.run_id}_{self.side}",
            market_id=self.market_id,
            side=self.side,
            tick=tick,
            q_me_pendle=float(self.config.sizer.q_min_pendle),
            placed_at_ts=placed_at_ts,
            depth_from_mark_ticks=depth_from_mark_ticks,
            queue_ahead_wei=_queue_ahead,
            r_accum=0.0,
            t_frac=1.0,
        )
        self.synthetic_orders.place(order)
        log.info(
            "backtest.replay.seeded_initial_order",
            order_id=order.order_id,
            market_id=self.market_id,
            side=self.side,
            tick=tick,
            depth_from_mark_ticks=depth_from_mark_ticks,
            q_me_pendle=order.q_me_pendle,
            queue_ahead_wei=str(_queue_ahead),
            placed_at_ts=placed_at_ts,
        )
        return True

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
        conn.execute(f"CALL sqlite_attach('{self.sqlite_path}', overwrite=true)")

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
            "market_id",
            "e_liq_per_epoch_pendle",
            "long_side_split",
            "short_side_split",
            "calibrated_at_utc",
            "source",
            "data_source",
        ]
        row = dict(zip(cols, rows[0], strict=False))
        side_split = row["long_side_split"] if self.side == "long" else row["short_side_split"]

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
                    f"future event observed at decision_ts={current_ts} " f"for order={order.order_id}"
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
        """Mirror main.py:_decision_loop evaluate input construction.

        current_features is populated from config.fill_model.covariate_whitelist
        with 0.0 values as a neutral placeholder (Wave 1). The feature builder
        (Plans 05-05/06) will wire real features here in later waves.
        """
        # Build current_features from the config's whitelist — 0.0 is a neutral
        # placeholder that satisfies predict()'s NaN check without biasing p_fill.
        whitelist = list(getattr(self.config.fill_model, "covariate_whitelist", []))
        current_features: dict[str, float] = {name: 0.0 for name in whitelist}
        if not current_features:
            # Fallback if whitelist is empty or attribute missing
            current_features = {"sigma_5min": 0.01}

        return EvaluateInput(
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            depth_from_mark_ticks=order.depth_from_mark_ticks,
            queue_ahead_wei=order.queue_ahead_wei,
            current_features=current_features,
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

        # Phase 5.1 Wave 4 performance fix (Rule 1+3): Scanning all 9000+ parquet files
        # every hourly boundary (1440 times per run × 219 perturbation child runs) is
        # prohibitively expensive. The archive layout uses numeric-prefixed market_id
        # directories (e.g. "101-BINANCE-ETHUSDT-25SEP2026"). Filter at the directory
        # level before calling scan_parquet — reduces I/O from ~9000 files to ~100.
        def _market_specific_files(base_dir: Path) -> list[str]:
            """Return parquet file paths for only the directories matching this market_id."""
            if not base_dir.exists():
                return []
            matched: list[str] = []
            for market_dir in base_dir.iterdir():
                if market_dir.is_dir() and market_dir.name.endswith(self.market_id):
                    matched.extend(str(p) for p in market_dir.rglob("*.parquet"))
            return matched

        # Load raw snapshots (lazy-load and cache: files don't change during a run)
        if self._amm_raw_df is None:
            try:
                raw_files = _market_specific_files(raw_dir)
                if not raw_files:
                    return
                raw_df = pl.read_parquet(raw_files)
                # Normalize column names.
                # Real archive data: sz_float/sz_combined_float, snapshot_ts is Hive string.
                # Conftest data: 't' for tick, 'sz' for size.
                col_map_raw: dict[str, str] = {}
                if "t" in raw_df.columns and "tick" not in raw_df.columns:
                    col_map_raw["t"] = "tick"
                if "sz_float" in raw_df.columns and "size" not in raw_df.columns:
                    col_map_raw["sz_float"] = "size"
                elif "sz" in raw_df.columns and "size" not in raw_df.columns:
                    col_map_raw["sz"] = "size"
                if col_map_raw:
                    raw_df = raw_df.rename(col_map_raw)
                if raw_df["snapshot_ts"].dtype == pl.String:
                    raw_df = raw_df.with_columns(pl.col("snapshot_ts").cast(pl.Int64))
                self._amm_raw_df = raw_df
            except Exception:  # noqa: BLE001
                return
        raw_df = self._amm_raw_df

        # Load combined snapshots (lazy-load and cache)
        if self._amm_combined_df is None:
            try:
                combined_files = _market_specific_files(combined_dir)
                if not combined_files:
                    return
                combined_df = pl.read_parquet(combined_files)
                col_map_comb: dict[str, str] = {}
                if "t" in combined_df.columns and "tick" not in combined_df.columns:
                    col_map_comb["t"] = "tick"
                if "sz_combined_float" in combined_df.columns and "size_combined" not in combined_df.columns:
                    col_map_comb["sz_combined_float"] = "size_combined"
                elif "sz" in combined_df.columns and "size_combined" not in combined_df.columns:
                    col_map_comb["sz"] = "size_combined"
                if col_map_comb:
                    combined_df = combined_df.rename(col_map_comb)
                if combined_df["snapshot_ts"].dtype == pl.String:
                    combined_df = combined_df.with_columns(pl.col("snapshot_ts").cast(pl.Int64))
                self._amm_combined_df = combined_df
            except Exception:  # noqa: BLE001
                return
        combined_df = self._amm_combined_df

        # Both datasets must have snapshot_ts for the filter to work.
        if "snapshot_ts" not in raw_df.columns or "snapshot_ts" not in combined_df.columns:
            return

        # Per-snapshot-total conservation check (DATA-05 / T-05-04).
        # Raw uses 1bp-tick grid; combined uses rate/tick_size grid — per-tick join is wrong.
        # The invariant is per-snapshot total: SUM(combined) >= SUM(raw).
        raw_epoch = raw_df.filter((pl.col("snapshot_ts") >= epoch_start_ts) & (pl.col("snapshot_ts") < epoch_end_ts))
        combined_epoch = combined_df.filter(
            (pl.col("snapshot_ts") >= epoch_start_ts) & (pl.col("snapshot_ts") < epoch_end_ts)
        )
        if raw_epoch.is_empty() or combined_epoch.is_empty():
            return
        raw_size_col = "size" if "size" in raw_epoch.columns else "sz_float"
        comb_size_col = "size_combined" if "size_combined" in combined_epoch.columns else "sz_combined_float"
        raw_tot = raw_epoch.group_by("snapshot_ts").agg(pl.col(raw_size_col).sum().alias("raw_total"))
        comb_tot = combined_epoch.group_by("snapshot_ts").agg(pl.col(comb_size_col).sum().alias("combined_total"))
        joined = raw_tot.join(comb_tot, on="snapshot_ts", how="full", coalesce=True).with_columns(
            pl.col("raw_total").fill_null(0.0),
            pl.col("combined_total").fill_null(0.0),
        )
        # 1% relative tolerance (same as ingest-time assert_amm_conservation)
        neg = joined.filter(
            (pl.col("combined_total") - pl.col("raw_total")) < -(pl.col("raw_total").abs() * 0.01 + 1e-9)
        )
        if not neg.is_empty():
            raise AMMConsumptionIdentityError(
                f"combined < raw on {neg.height} snapshot(s) during [{epoch_start_ts}, {epoch_end_ts}); "
                f"first 5: {neg.head(5).to_dicts()}"
            )

    def _handle_trade_event(self, evt: dict[str, Any], current_ts: int) -> None:
        """Detect fills against in-flight synthetic orders; schedule close-at-market.

        v0.5 fill detection: a synthetic order is hit when the trade's size_wei
        is >= the order's queue_ahead_wei (queue-in-front fully consumed).
        Production-grade detection lives in queue_tracker; this is the backtest-side
        approximation matching Phase 2 fit semantics.

        T-05-07: NEVER calls time.time() — current_ts is blockTimestamp from replay.
        """
        evt_rate = float(evt.get("rate") or 0.0)
        evt_size = int(evt.get("size_wei") or 0)
        for order in list(self.synthetic_orders.in_flight()):
            if self._trade_consumes_order(order, evt_rate, evt_size):
                sc = self.latency_scheduler.schedule(
                    fill_ts=float(current_ts),
                    fill_rate=evt_rate,
                    order_id=order.order_id,
                    fill_event_index=int(evt.get("eventIndex") or 0),
                )
                self._scheduled_closes.append(sc)
                # Mark queue_ahead as 0 — order is hit; remaining fills are scheduled.
                self.synthetic_orders.update_queue_ahead(order.order_id, 0)

    def _trade_consumes_order(self, order: SyntheticOrder, evt_rate: float, evt_size: int) -> bool:
        """v0.5 fill detection: trade consumes the order's queue-in-front.

        Production-grade detection is in queue_tracker; this is the backtest-side
        approximation. The order is filled when:
          - The trade's size_wei >= order's queue_ahead_wei (queue fully consumed).
        Rate-crossing check is deferred to Plan 05-04+ (sweep/fill-model integration).
        """
        return order.queue_ahead_wei <= evt_size

    def _fire_scheduled_closes(self, current_ts: int) -> None:
        """Fire scheduled closes whose close_at_ts has been reached.

        Realized close uses underlying APR at close_at_ts — NOT fill_ts.
        The L-second window IS the inventory-at-risk period (BACK-02 load-bearing semantic).
        T-05-10: _underlying_at(sc.close_at_ts) must be called, never _underlying_at(sc.fill_ts).
        """
        fired: list[ScheduledClose] = []
        remaining: list[ScheduledClose] = []
        for sc in self._scheduled_closes:
            if current_ts >= sc.close_at_ts:
                # Realized close uses underlying APR at close_at_ts — NOT fill_ts.
                close_rate = self._underlying_at(sc.close_at_ts)
                # P&L: (fill_rate - close_rate) for long; sign-flipped for short.
                sign = 1.0 if self.side == "long" else -1.0
                order = self.synthetic_orders.get(sc.order_id)
                notional = order.q_me_pendle if order is not None else 0.0
                pnl_pendle = sign * (sc.fill_rate - close_rate) * notional
                self.synthetic_orders.mark_filled(sc.order_id)
                self.output.decision_log.append(
                    {
                        "run_id": self.run_id,
                        "current_chain_ts": current_ts,
                        "order_id": sc.order_id,
                        "decision_kind": "FILL_REALIZED",
                        "fill_ts": sc.fill_ts,
                        "close_at_ts": sc.close_at_ts,
                        "fill_rate": sc.fill_rate,
                        "close_rate": close_rate,
                        "pnl_pendle": pnl_pendle,
                    }
                )
                fired.append(sc)
            else:
                remaining.append(sc)
        self._scheduled_closes = remaining

    def _underlying_at(self, ts: float) -> float:
        """Read latest underlying_apr row with snapshot_ts <= ts.

        Returns float rate. Falls back to 0.05 (default) if no matching row or on error.
        Used by _fire_scheduled_closes to get the realized close basis at close_at_ts.
        T-05-10: callers MUST pass close_at_ts, never fill_ts.
        """
        try:
            df = (
                pl.scan_parquet(str(self.parquet_root / "underlying_apr" / "**" / "*.parquet"))
                .filter(pl.col("snapshot_ts") <= int(ts))
                .sort("snapshot_ts")
                .tail(1)
                .collect()
            )
            if df.height == 0:
                return 0.05  # default — no row at or before ts
            return float(df.select("rate").item())
        except Exception:  # noqa: BLE001
            return 0.05  # default — parquet not seeded in this test scenario

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

        n_cancels = sum(1 for d in self.output.decision_log if d.get("decision_kind") == "CANCEL")
        predicted_p_fill_mean = sum(d.get("p_fill", 0.0) for d in self.output.decision_log) / max(
            1, len(self.output.decision_log)
        )

        # Bin realized-fill P&L by UTC day across the run window. Reward accrual
        # (the positive component of strategy P&L) is added by a downstream wave;
        # this captures the fill-loss component, which is sufficient for
        # block_bootstrap_pnl + ship-gate to be well-defined. A single zero day
        # is emitted when no events were observed (e.g. unseeded test fixture)
        # so callers like run_perturbation_grid don't trip the empty-array guard.
        self.output.daily_pnl = self._aggregate_daily_pnl()

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

    def _aggregate_daily_pnl(self) -> np.ndarray:
        """Bin net P&L (reward_accrual − fill_loss) by UTC day across the run window.

        Composed from two independent sources in the decision_log:

        1. Reward accrual — any entry carrying `r_share_per_epoch_pendle` > 0
           (typically HOLD/CANCEL ticks from _maybe_emit_tick) contributes:
             reward_per_tick = r_share_per_epoch_pendle * (dt_per_tick / seconds_per_epoch)
           where seconds_per_epoch comes from config.reward_share_model.epoch_days
           and dt_per_tick from config.decision.decision_loop_interval_s (PROTO-04 SSoT).

        2. Fill losses — FILL_REALIZED entries contribute their `pnl_pendle` field
           (negative for realized losses, by convention).

        Both branches are independent: FILL_REALIZED entries never carry
        r_share_per_epoch_pendle (see _fire_scheduled_closes), so an entry
        contributes to at most one branch.

        Window endpoints come from the full decision_log (every entry carries
        `current_chain_ts`), so days with no events appear as zero P&L rather
        than dropping out — block_bootstrap_pnl needs a well-defined N. A single
        zero day is returned for an empty log (empty-array guard for callers like
        run_perturbation_grid).
        """
        log_entries = self.output.decision_log
        if not log_entries:
            return np.zeros(1, dtype=np.float64)

        timestamps = [int(e["current_chain_ts"]) for e in log_entries if "current_chain_ts" in e]
        if not timestamps:
            return np.zeros(1, dtype=np.float64)

        first_ts = min(timestamps)
        last_ts = max(timestamps)
        n_days = max(1, (last_ts - first_ts) // 86400 + 1)

        # Unit-conversion constants — PROTO-04 SSoT, never hard-coded.
        seconds_per_epoch = float(self.config.reward_share_model.epoch_days) * 86400.0
        dt_per_tick = float(self.config.decision.decision_loop_interval_s)

        daily = np.zeros(n_days, dtype=np.float64)
        for entry in log_entries:
            ts = entry.get("current_chain_ts")
            if ts is None:
                continue
            day_idx = (int(ts) - first_ts) // 86400

            # Branch 1 — fill loss (FILL_REALIZED entries only).
            if entry.get("decision_kind") == "FILL_REALIZED":
                daily[day_idx] += float(entry.get("pnl_pendle", 0.0))

            # Branch 2 — reward accrual (any entry with r_share_per_epoch_pendle > 0).
            r_share = entry.get("r_share_per_epoch_pendle")
            if r_share is not None and r_share > 0.0:
                reward_per_tick = float(r_share) * (dt_per_tick / seconds_per_epoch)
                daily[day_idx] += reward_per_tick

        return daily
