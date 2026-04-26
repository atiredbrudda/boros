"""GasHistoryCache — DECIDE-03 EWMA cancel_cost computation.

The single authoritative source of the cancel_cost_pendle value used in the
EV equation. All other files in decision/ that need cancel_cost MUST use this
class — the no_hardcoded_cancel_cost_lint.py pre-commit hook mechanically
enforces this invariant (ALLOWED_FILES = {gas_history.py}).

Algorithm
---------
Fetches ``eth_feeHistory`` from Arbitrum (100-block window) once per TTL
(default 60 s). Applies EWMA(alpha=0.1) over the base_fee+tip samples to
smooth out short spikes, then converts:

    wei = EWMA(gas_price_wei) × cancel_gas_units_estimate
    eth = wei / 1e18
    usd = eth × config.pricing.eth_price_usd
    pendle = usd / config.pricing.pendle_price_usd

On RPC failure or timeout (5 s budget), returns the last known value so the
1 Hz decision loop is never blocked.

References
----------
[[gas-history-ewma-cancel-cost]] — DECIDE-03 spec, wei→PENDLE path, EWMA
    parameter justification, daily-rescreen discipline.
PITFALLS §C5 (Phase 4 #5): hardcoded cancel_cost scalar violates DECIDE-03.
    The lint script (no_hardcoded_cancel_cost_lint.py) catches regressions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from ..config.schema import BotConfig
from ..data import chain_time

log = structlog.get_logger(__name__)

__all__ = ["GasHistoryCache"]


@dataclass
class GasHistoryCache:
    """TTL-cached EWMA of Arbitrum gas prices, converted to PENDLE-units cancel cost.

    Attributes
    ----------
    last_fetch_chain_ts:
        Chain timestamp (Unix seconds) of the last successful fee_history fetch.
        0 means the cache is cold (never fetched). The TTL check also guards on
        this sentinel so the first call always fetches unconditionally.
    last_value_pendle:
        The most recently computed cancel_cost in PENDLE units. Returned as a
        stale-but-known value on RPC failure.
    ewma_state:
        Running EWMA accumulator in wei. Seeded with the first sample on first
        fetch; updated on each subsequent fetch.
    """

    last_fetch_chain_ts: int = 0
    last_value_pendle: float = 0.0
    ewma_state: float = field(default=0.0)

    async def cancel_cost_pendle(self, *, w3: Any, config: BotConfig) -> float:
        """Return cancel_cost in PENDLE, fetching fee_history at most once per TTL.

        Parameters
        ----------
        w3:
            AsyncWeb3 instance (from ``rpc_client.make_arbitrum_rpc``).
            Accepts ``None`` during unit tests where fee_history is mocked — the
            gas cache handles the ``None`` case by returning ``last_value_pendle``
            (stale-but-known).
        config:
            Live BotConfig. Reads:
            - ``decision.cancel_cost_ttl_s`` — TTL in seconds (default 60)
            - ``decision.cancel_cost_ewma_alpha`` — EWMA alpha (default 0.1)
            - ``decision.cancel_cost_block_window`` — blocks to fetch (default 100)
            - ``execution.cancel_gas_units_estimate`` — gas units estimate
            - ``pricing.eth_price_usd`` — operator-calibrated USD/ETH price
            - ``pricing.pendle_price_usd`` — operator-calibrated USD/PENDLE price
        """
        # ── TTL check ────────────────────────────────────────────────────────
        ttl = config.decision.cancel_cost_ttl_s

        # Get current time — use chain_time singleton (installed by main.py at startup).
        # In tests/early startup where the singleton is not yet installed, fall back to
        # asyncio monotonic time offset by a large epoch value so the sentinel (== 0)
        # check still works correctly.
        try:
            now_int = int(await chain_time.now_cached())
        except RuntimeError:
            # chain_time singleton not installed — safe fallback for tests / early startup.
            # Adding 1_700_000_000 ensures the value is non-zero on the very first call
            # even if asyncio loop time is near zero.
            now_int = int(asyncio.get_event_loop().time()) + 1_700_000_000

        if self.last_fetch_chain_ts != 0 and (now_int - self.last_fetch_chain_ts) < ttl:
            return self.last_value_pendle

        # ── Fetch fee_history ─────────────────────────────────────────────────
        if w3 is None:
            # w3 not provided (tests with zero-cost gas mock) — return cached
            return self.last_value_pendle

        block_window = config.decision.cancel_cost_block_window
        try:
            hist = await asyncio.wait_for(
                w3.eth.fee_history(block_window, "latest", [50]),
                timeout=5.0,
            )
        except (TimeoutError, Exception) as exc:
            log.warning(
                "gas_history.fetch_failed",
                err=str(exc),
                last_value_pendle=self.last_value_pendle,
            )
            return self.last_value_pendle

        # ── Build gas-price samples ───────────────────────────────────────────
        # baseFeePerGas has block_window+1 entries (includes next block estimate);
        # drop the last entry to match the block_window count.
        # web3.py returns an AttributeDict (supports both attr and item access);
        # test mocks use plain objects with attribute access only — use getattr.
        raw_base_fees = getattr(hist, "baseFeePerGas", [])
        base_fees = list(raw_base_fees[:-1]) if raw_base_fees else []
        # reward is a list-of-lists; take the 50th-percentile tip (index 0 after [50]).
        raw_reward = getattr(hist, "reward", []) or []
        priority = [r[0] if r else 0 for r in raw_reward]
        # Pad priority with zeros if shorter than base_fees (edge case on very new chains).
        while len(priority) < len(base_fees):
            priority.append(0)
        samples = [int(b) + int(p) for b, p in zip(base_fees, priority[: len(base_fees)], strict=False)]

        # ── EWMA ─────────────────────────────────────────────────────────────
        alpha = config.decision.cancel_cost_ewma_alpha
        if not samples:
            log.warning("gas_history.empty_samples", last_value_pendle=self.last_value_pendle)
            return self.last_value_pendle

        # Seed EWMA with the first sample if cold; otherwise continue the running state.
        ewma = self.ewma_state if self.ewma_state else float(samples[0])
        for s in samples[1:]:
            ewma = alpha * float(s) + (1.0 - alpha) * ewma
        self.ewma_state = ewma

        # ── Wei → PENDLE conversion ───────────────────────────────────────────
        gas_units = config.execution.cancel_gas_units_estimate
        wei = ewma * gas_units
        eth = wei / 1e18
        usd = eth * config.pricing.eth_price_usd
        pendle = usd / config.pricing.pendle_price_usd

        self.last_value_pendle = float(pendle)
        self.last_fetch_chain_ts = now_int
        return self.last_value_pendle
