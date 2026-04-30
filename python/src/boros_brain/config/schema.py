"""
Pydantic v2 BotConfig — THE single source of truth for every knob in the system.

Invariants (PROTO-04):
  - extra='forbid' + frozen=True on every sub-model → adding a knob in code without
    adding it here is mechanically impossible (the model_dump round-trip test catches it).
  - No `submission_path` field — dropped per P0-04 (Send Txs Bot is the mandatory lane).
  - `voluntary_cancel_forfeits_accumulated: bool = False` default locked per P0-01
    ([[Voluntary cancel reward behavior]]).
  - `markets` list capped to max_length=1 for v0.5 single-market regime.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..backtest.config import BacktestConfig
from ..decision.config import DecisionEngineConfig
from ..fill_model.config import FillModelConfig
from ..loss_model.config import LossModelConfig
from ..pricing.config import PricingConfig
from ..reward_model.config import RewardShareModelConfig
from ..sizer.config import SizerConfig


class StrictBase(BaseModel):
    """Base for every BotConfig sub-model.

    `extra='forbid'` turns unknown YAML keys into a loud ValidationError.
    `frozen=True` prevents runtime mutation of a loaded BotConfig — knobs are
    authored in YAML, loaded once, and then read-only for the lifetime of the run.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class StrategyConfig(StrictBase):
    """Strategy knobs — EV rule inputs and reward-share policy."""

    voluntary_cancel_forfeits_accumulated: bool = False
    """D-01 / P0-01 lock ([[Voluntary cancel reward behavior]]).

    Boros official team statement: 'LO incentives are calculated per block, so
    accumulated rewards won't go to zero even if users cancel the order.' The EV
    cancel rule is therefore forward-looking. The punitive branch is retained as
    dead-code in the engine for sensitivity backtesting only.
    """

    target_share: float = Field(0.05, ge=0.01, le=1.0)
    """Target reward share per-market. Caps at 1.0 (full side), floors at 1%."""


class ExecutionConfig(StrictBase):
    """Execution knobs — agent wallet + cancel-latency budget.

    NOTE: NO `submission_path` field. That knob was dropped per P0-04 — Send Txs Bot
    is the mandatory submission lane; direct-to-chain is ruled out. Any test that
    asserts `submission_path` not in the schema is a regression guard against this
    knob silently creeping back.
    """

    cancel_latency_budget_s: float = 5.0
    require_success_default: bool = True
    agent_wallet_gas_warn_multiples: int = 50
    agent_wallet_gas_halt_multiples: int = 20
    agent_wallet_gas_emergency_multiples: int = 5
    cancel_gas_units_estimate: int = Field(200_000, ge=10_000, le=2_000_000)
    """Gas units estimate for a cancel transaction (DECIDE-03 cancel_cost calculation).

    Used in GasHistoryCache.cancel_cost_pendle: cost_wei = baseFeePerGas_ewma × gas_units.
    Default 200k is conservative for Arbitrum cancel calldata size.
    """
    entrance_fee_pendle: float = Field(0.0, ge=0.0)
    """Per-market entrance fee in PENDLE units (SAFE-07 migration cost estimate).

    Set to the actual entrance fee at market open; used by MaturityBreaker to
    estimate migration cost. Default 0.0 — override per market at re-screen.
    """


class DataConfig(StrictBase):
    """Data-pipeline knobs — poll intervals, RPC URL, Boros REST base."""

    markets_poll_interval_s: float = 30.0
    e_liq_poll_interval_s: float = 5.0
    chain_time_cache_ttl_s: float = 1.0
    rpc_url_arbitrum: str  # no default — operator MUST supply explicitly
    boros_rest_base: str = "https://api.boros.finance/open-api/v1"
    margin_poll_interval_s: float = Field(1.0, ge=0.1, le=60.0)
    """SAFE-01 — 1 Hz cadence matching the decision loop.

    MarginPoller calls POST /accounts/get-net-margin at this interval.
    """
    boros_account_id: int = Field(0, ge=0)
    """Boros account_id for /accounts/get-net-margin. Operator-supplied. 0 = unset."""


class InfraConfig(StrictBase):
    """Infra knobs — SQLite path, ZMQ endpoints, heartbeat, chain-drift bands.

    Two-endpoint PUB/SUB topology (checker issue #07): each tier binds its own
    PUB endpoint and SUBs the other — no string-mangling in the 01-03 EventBus.
    """

    sqlite_path: str = "state/state.sqlite"
    logs_dir: str = "logs"
    zmq_cmd_endpoint: str = "ipc:///tmp/boros.cmd"
    zmq_events_brain_endpoint: str = "ipc:///tmp/boros.events.brain"
    zmq_events_hands_endpoint: str = "ipc:///tmp/boros.events.hands"
    zmq_kill_endpoint: str = "ipc:///tmp/boros.cmd.kill"
    heartbeat_interval_s: float = 5.0
    heartbeat_timeout_misses: int = 3
    chain_drift_warn_s: float = 5.0
    chain_drift_halt_s: float = 30.0


class ScreenerConfig(StrictBase):
    """Market-screener knobs — window lengths and thresholds for the economics gate."""

    min_time_to_maturity_days: int = 30
    trades_window_days: int = 60
    realized_vol_window_days: int = 14
    reversal_count_window_days: int = 3
    alt_yield: float = Field(0.05, ge=0.0, le=1.0)
    fill_loss_coarse_bound: float = Field(0.02, ge=0.0, le=1.0)


class MarketRewardCalibration(StrictBase):
    """LOCKED D-01 (2026-04-24): operator-manual per-market reward-budget calibration.

    Refreshed at daily re-screen via the calibrate CLI subcommand. Mirrored into
    the new state.market_reward_calibration SQLite table with
    `data_source='operator'` CHECK constraint (see
    python/src/boros_brain/state/writers/market_reward_calibration.py).

    Replaces the Phase 1 UAT ELiqPoller carried concern — `liquidityRewardPerEpoch`,
    `longBudget`, `shortBudget` are NOT in the live `/open-api/v1/markets`
    response; the operator pastes values from Pendle docs / dApp UI / team
    announcements. See [[e-liq-per-epoch-source-decision]] for the full evidence
    log and [[market-reward-calibration-operator-workflow]] for the runbook.

    W2a (Phase 05.2): Added `effective_at_utc` and `next_refresh_at_utc` to
    support epoch-keyed calibration rows. See [[phase-05-2-alembic-0008]].
    """

    e_liq_per_epoch_pendle: float = Field(..., ge=0.0)
    long_side_split: float = Field(..., ge=0.0, le=1.0)
    short_side_split: float = Field(..., ge=0.0, le=1.0)
    calibrated_at_utc: str  # ISO8601
    effective_at_utc: str  # ISO8601 — when this calibration becomes authoritative (W2a)
    next_refresh_at_utc: str  # ISO8601 — when operator should re-check (W2a)
    source: Literal["dapp_ui", "team_statement", "pendle_docs"] = "dapp_ui"

    @field_validator("short_side_split")
    @classmethod
    def _splits_sum_to_one(cls, v: float, info) -> float:  # type: ignore[no-untyped-def]
        """P3-4 operator-error guard. long + short MUST equal 1.0 (1e-9 tolerance)."""
        long = info.data.get("long_side_split")
        if long is not None and abs(long + v - 1.0) > 1e-9:
            raise ValueError(
                f"long_side_split + short_side_split must == 1.0 "
                f"(got {long} + {v} = {long + v}). "
                "P3-4 operator-error guard."
            )
        return v

    @field_validator("effective_at_utc", "next_refresh_at_utc")
    @classmethod
    def _must_look_like_iso8601(cls, v: str) -> str:
        """Minimal ISO8601 sanity check — must start with YYYY-MM-DDT."""
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}T", v):
            raise ValueError(
                f"expected ISO8601 string (YYYY-MM-DDT...), got {v!r}"
            )
        return v


class MarketCalibration(StrictBase):
    """Per-market calibration (OU params + CLO bands + oracle addr + maturity).

    Plan 03-02 added `reward_calibration` (Optional MarketRewardCalibration)
    for the LOCKED D-01 operator-manual reward-budget calibration. Until the
    operator runs `python -m boros_brain.reward_model calibrate ...`, this
    field stays None and downstream Sizer (Plan 03-03) reads from
    state.market_reward_calibration directly.
    """

    market_id: str
    scale: float
    s: float
    clo_lower_thresh: float
    clo_upper_thresh: float
    fIndex_oracle_address: str
    maturity_ts: int
    reward_calibration: MarketRewardCalibration | None = None  # NEW Plan 03-02
    max_update_delay_s: int = Field(600, ge=60, le=86400)
    """SAFE-02: maxUpdateDelay for this market's oracle (seconds).

    OracleStaleBreakerConfig.fraction_of_max × max_update_delay_s is the
    trip threshold. Default 600s (10min) is a conservative placeholder —
    override per market from on-chain contract reads.
    """
    underlying_exchange: Literal["binance", "okx", "hyperliquid"] = "binance"
    """The exchange that provides the underlying rate feed for this market."""

    underlying_symbol: str = Field("", max_length=64)
    """The exchange-specific symbol for the underlying rate feed (e.g. ETHUSDT).

    Empty string = unset. SAFE-09 underlying staleness breaker uses this to
    look up the correct parquet partition in underlying_apr/.
    """

    margin_per_yu_usd: float | None = Field(None, ge=0.01, le=10_000_000.0)
    """Per-market USD margin per 1 YU at slider=0% (min margin). Operator-calibrated
    from dapp UI funded trial-order panels (slider-invariant per-YU primitive).
    None means inherit from BotConfig.sizer.margin_per_yu_usd (single-market regime
    backwards compat). For BINANCE-ETHUSDT-25SEP2026: .30/YU at  ETH baseline.
    See [[phase-05-2-margin-per-yu-rename]].
    """

    daily_volatility_pct: float | None = Field(None, ge=0.0, le=100.0)
    """7DMA implied APR daily volatility from dapp UI 'Daily Volatility' badge (percent).
    Drives liquidation_buffer floor: liquidation_buffer_pct >= liquidation_buffer_safety_n
    × daily_volatility_pct. For BINANCE-ETHUSDT-25SEP2026: 0.34% per W0 E2.
    """

    liquidation_buffer_safety_n: int = Field(3, ge=1, le=20)
    """Liquidation-buffer multiplier N. Default 3 means 3× daily volatility.
    Operator tunes this knob based on fill-risk tolerance.
    """


class BotConfig(StrictBase):
    """Top-level config. One instance per run; frozen after load."""

    mode: Literal["live", "paper", "backtest", "ingest", "screen"]
    strategy_version: str
    market_id: str
    side: Literal["long", "short"]
    root_wallet_address: str
    agent_wallet_address: str

    # Bare type: ignore (no error code) is intentional: mypy fires [arg-type] on these
    # Pydantic default_factory=ModelClass lines only when the pydantic mypy plugin is
    # absent. With the plugin, no error appears. A bare ignore suppresses either case
    # without triggering [unused-ignore] when the plugin is installed.
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)  # type: ignore
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)  # type: ignore
    data: DataConfig
    infra: InfraConfig = Field(default_factory=InfraConfig)  # type: ignore
    screener: ScreenerConfig = Field(default_factory=ScreenerConfig)  # type: ignore
    fill_model: FillModelConfig = Field(default_factory=FillModelConfig)  # type: ignore
    loss_model: LossModelConfig = Field(default_factory=LossModelConfig)  # type: ignore
    reward_share_model: RewardShareModelConfig = Field(default_factory=RewardShareModelConfig)  # type: ignore
    pricing: PricingConfig = Field(default_factory=PricingConfig)  # type: ignore
    # Plan 03-03 — SizerConfig attachment (deferred from 03-02 because sizer
    # imports from loss_model + reward_model which are 03-01/02 artifacts).
    sizer: SizerConfig = Field(default_factory=SizerConfig)  # type: ignore
    # Plan 04-02 — DecisionEngineConfig attachment (~25 new knob leaves).
    decision: DecisionEngineConfig = Field(default_factory=DecisionEngineConfig)  # type: ignore
    # Plan 05-01 — BacktestConfig attachment (PROTO-04 SSoT for Phase-5 knobs).
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)  # type: ignore
    markets: list[MarketCalibration] = Field(default_factory=list, max_length=1)
