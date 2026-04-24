"""DATA-06 — /markets poller. Default cadence 30s (configurable via config.data.markets_poll_interval_s).

Per poll, for each market we capture (clo_lower_thresh, clo_upper_thresh, f_index_raw)
where f_index_raw is the decoded floatingIndex_raw from the per-market fIndexOracle
(DATA-07 reader). Rows are appended to clo_history ONLY when the tuple changes — keeps the
table compact while ensuring 01-11 SCALE calibration has two (clo, fIndex) pairs
≥ 1 day apart.

Schema reconciliation: the /markets response shape was found to be:
  {results: [...], total, skip, syncStatus}
NOT a bare list. CLO thresholds are nested under config.cloLowerThresh/cloUpperThresh.
fIndexOracle is nested under config.fIndexOracle. See docs/samples/markets-schema-notes.md.

Threat mitigations:
  T-01-09-01: extra='allow' on Pydantic schema — new fields logged at INFO, not fatal.
  T-01-09-02: FIndexDecodeError is non-fatal; row written with f_index_raw=NULL + WARN.
  T-01-09-03: Exponential backoff [base, 2x, 4x] + jitter on 429/5xx; cap 3 retries.
"""

from __future__ import annotations

import asyncio
import random

import httpx
import structlog

from boros_brain.config.schema import BotConfig
from boros_brain.data.chain_time import now_cached
from boros_brain.data.findex_reader import FIndexReader
from boros_brain.data.rest_client import make_boros_rest_client
from boros_brain.state.writers.clo_history import insert_clo_history

from .schemas import Market, MarketsResponse

log = structlog.get_logger(__name__)


class MarketsPoller:
    """Polls GET /markets on a configurable cadence and writes CLO+fIndex changes to clo_history.

    Args:
        config: Live BotConfig. Reads data.markets_poll_interval_s and infra.sqlite_path.
        http: Pre-built httpx.AsyncClient (base_url already set to boros_rest_base).
        run_id: Active run ID from the RUN_MANIFEST (carried in log context).
        w3: Shared AsyncWeb3 instance (caller owns lifecycle). Used to lazily construct
            FIndexReader instances for markets not pre-wired via findex_readers. If None
            and a market is encountered without a pre-wired reader, RuntimeError is raised.
            Pass an AsyncWeb3 from make_arbitrum_rpc() — do NOT create one per call (WR-04).
        findex_readers: Optional pre-built per-market FIndexReader instances keyed by
            imData.symbol (e.g. "BINANCE-ETHUSDT-29MAY2026"). Supplied explicitly by
            tests (mockable) and by main.py when wiring is centralized. If None, the
            poller lazily creates a reader per market using w3 on first encounter.
        backoff_base_s: Base backoff delay for exponential retry on 5xx (default 0.5s;
            set to 0.01s in tests to keep test suite fast).
    """

    def __init__(
        self,
        config: BotConfig,
        http: httpx.AsyncClient,
        run_id: str,
        w3: object | None = None,
        findex_readers: dict[str, FIndexReader] | None = None,
        backoff_base_s: float = 0.5,
    ) -> None:
        self.config = config
        self.http = http
        self.run_id = run_id
        self._w3 = w3  # shared AsyncWeb3 — caller owns lifecycle (WR-04)
        # Cache: market symbol → (clo_lower_thresh, clo_upper_thresh, f_index_raw)
        self._last: dict[str, tuple[float, float, int | None]] = {}
        self._findex_readers: dict[str, FIndexReader] = dict(findex_readers or {})
        self._backoff_base_s = backoff_base_s

    async def poll_once(self) -> list[Market]:
        """One HTTP GET /markets + Pydantic validation. Retries on 5xx with exponential backoff.

        Returns the parsed list of Market objects.
        Raises on 4xx or after exhausting all retry attempts on 5xx.
        """
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = await self.http.get("/markets")
                if resp.status_code == 200:
                    parsed = MarketsResponse.model_validate_json(resp.content)
                    # T-01-09-01: log unknown top-level fields at INFO
                    if parsed.model_extra:
                        log.info("markets_poller.unknown_fields", fields=list(parsed.model_extra.keys()))
                    return parsed.results
                if 500 <= resp.status_code < 600:
                    # 5xx: raise to trigger retry
                    raise httpx.HTTPStatusError(
                        f"5xx response {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                # 4xx: raise immediately (not retryable)
                resp.raise_for_status()
            except (httpx.HTTPStatusError, httpx.HTTPError) as exc:
                if attempt == max_attempts - 1:
                    log.error(
                        "markets_poller.permanent_error",
                        attempt=attempt,
                        err=str(exc),
                    )
                    raise
                delay = self._backoff_base_s * (2**attempt) + random.uniform(0, self._backoff_base_s * 0.5)
                log.warning(
                    "markets_poller.transient_error",
                    attempt=attempt,
                    delay_s=round(delay, 3),
                    err=str(exc),
                )
                await asyncio.sleep(delay)
        return []  # unreachable — loop always raises or returns

    async def tick(self) -> int:
        """Run one poll cycle + write changes to clo_history. Returns number of rows written.

        For each market:
          1. Parse clo_lower_thresh, clo_upper_thresh from /markets config.*
          2. Decode floatingIndex_raw via per-market fIndexOracle (DATA-07)
          3. Compare (clo_lower, clo_upper, f_index_raw) against previous snapshot
          4. insert_clo_history ONLY on change (keeps clo_history compact)
        """
        raw_markets = await self.poll_once()
        snapshot_ts = await now_cached()
        written = 0

        # Deduplicate by symbol — the API occasionally returns the same symbol twice
        # (e.g. HYPERLIQUID-BTC-29MAY2026). Keep first occurrence; log duplicates.
        seen: set[str] = set()
        markets = []
        for m in raw_markets:
            sym = m.im_data.symbol
            if sym in seen:
                log.warning("markets_poller.duplicate_symbol_skipped", symbol=sym)
            else:
                seen.add(sym)
                markets.append(m)

        for m in markets:
            symbol = m.im_data.symbol  # string market identifier (e.g. "BINANCE-ETHUSDT-29MAY2026")
            clo_lower = m.config.clo_lower_thresh
            clo_upper = m.config.clo_upper_thresh
            findex_oracle_addr = m.config.findex_oracle

            # Decode fIndex for this market (DATA-07).
            # If market has no fIndexOracle (zero addr / None), record f_index_raw=None.
            f_index_raw: int | None = None
            if findex_oracle_addr and findex_oracle_addr != "0x0000000000000000000000000000000000000000":
                reader = self._findex_readers.get(symbol)
                if reader is None:
                    # Lazy-create reader using the shared w3 instance (WR-04).
                    # w3 must be provided at construction time — creating one per market
                    # leaks one aiohttp session per unique symbol (never closed).
                    if self._w3 is None:
                        raise RuntimeError(
                            f"MarketsPoller: no w3 wired for market {symbol!r}. "
                            "Pass w3=<AsyncWeb3> to MarketsPoller.__init__ or "
                            "pre-populate findex_readers for every market. (WR-04)"
                        )
                    reader = FIndexReader(
                        w3=self._w3,
                        oracle_address=findex_oracle_addr,
                        ttl_s=self.config.data.chain_time_cache_ttl_s,
                    )
                    self._findex_readers[symbol] = reader
                try:
                    payload = await reader.get_latest_fIndex()
                    f_index_raw = int(payload["floatingIndex"])
                except Exception as exc:
                    # T-01-09-02: decode/RPC failure is non-fatal — still record CLO thresholds.
                    log.warning(
                        "markets_poller.findex_decode_failed",
                        market_id=symbol,
                        err=str(exc),
                    )

            prev = self._last.get(symbol)
            cur: tuple[float, float, int | None] = (clo_lower, clo_upper, f_index_raw)
            if prev != cur:
                insert_clo_history(
                    sqlite_path=self.config.infra.sqlite_path,
                    market_id=symbol,
                    snapshot_ts=snapshot_ts,
                    clo_lower_thresh=clo_lower,
                    clo_upper_thresh=clo_upper,
                    f_index_raw=f_index_raw,
                )
                self._last[symbol] = cur
                written += 1

        log.info(
            "markets_poller.tick_done",
            run_id=self.run_id,
            total=len(markets),
            written=written,
        )
        return written


async def run_markets_poller(config: BotConfig, run_id: str) -> None:
    """Long-running asyncio task — call from brain main.py.

    Loops forever at config.data.markets_poll_interval_s cadence.
    Exceptions from tick() are caught and logged; the loop continues.

    A single AsyncWeb3 instance is created here and shared across all FIndexReader
    instances for the lifetime of the poller (WR-04: prevents one leaked aiohttp
    session per market symbol encountered for the first time).
    """
    from boros_brain.data.rpc_client import make_arbitrum_rpc

    w3 = await make_arbitrum_rpc(config)
    async with make_boros_rest_client(config) as http:
        poller = MarketsPoller(config, http, run_id, w3=w3)
        while True:
            try:
                await poller.tick()
            except Exception as exc:
                log.exception("markets_poller.tick_failed", run_id=run_id, err=str(exc))
            await asyncio.sleep(config.data.markets_poll_interval_s)
