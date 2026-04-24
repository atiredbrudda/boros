"""DATA-07 — fIndexOracle reader. Decodes packed bytes26-in-bytes32 payload per
RESEARCH.md §Pattern 8 + boros_bot_guide.md L187-217.

The bytes26 decode math is in ``decode_findex_bytes`` — a pure function with no
RPC dependency so it can be unit-tested in isolation (test_findex_decode.py).

int112 sign extension: if the 112-bit floatingIndex value has its MSB set
(>= 2^111), subtract 2^112 to get the negative two's-complement value.

Threat mitigations (T-01-09-02):
  - Post-decode sanity bounds: |floatingIndex| < 2^110 — values outside this
    range indicate an off-by-one or wrong-endian decode.
  - Failures raise FIndexDecodeError (non-fatal in the poller — logged as WARN).
  - fTime staleness check is Phase 4 SAFE-02 concern (not checked here).

Exports:
  decode_findex_bytes(raw: bytes) -> dict    — pure function, unit-testable
  fIndex_display(floatingIndex, scale) -> float
  FIndexDecodeError
  FIndexReader                               — dataclass with TTL cache
  FINDEX_ABI
  KNOWN_ORACLES
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from web3 import AsyncWeb3

log = structlog.get_logger(__name__)


# ── ABI ────────────────────────────────────────────────────────────────────────

FINDEX_ABI = [
    {
        "name": "getLatestFIndex",
        "inputs": [],
        "outputs": [{"type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "name": "latestAnnualizedRate",
        "inputs": [],
        "outputs": [{"type": "int256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ── Known oracle addresses ─────────────────────────────────────────────────────
# Per RESEARCH.md §Pattern 8 lines 955-958 (verified against live /markets API response
# 2026-04-24: all three addresses confirmed present in docs/samples/markets-response.json).

KNOWN_ORACLES: dict[str, str] = {
    "BINANCE-ETHUSDT-29MAY2026": "0x1950dc94e3063267049482f075af72107eb79352",
    "BINANCE-ETHUSDT-26JUN2026": "0x9dd097e8e7b18a79ac86ddac72d0cdf72017198c",
    "BINANCE-ETHUSDT-25SEP2026": "0x7fe191632c66ddbd14d6fbe1e331744b894a2b7b",
    # Other markets: resolve per-market via /markets config.fIndexOracle (DATA-06)
}


# ── Exceptions ─────────────────────────────────────────────────────────────────


class FIndexDecodeError(RuntimeError):
    """Raised when decoded fIndex fields fail sanity bounds (T-01-09-02).

    Non-fatal in the poller — MarketsPoller catches this and writes
    f_index_raw=NULL with a WARN log.
    """


# ── Pure-function decoder ──────────────────────────────────────────────────────


def decode_findex_bytes(raw: bytes) -> dict[str, int]:
    """Decode the bytes32 payload returned by getLatestFIndex().

    Per boros_bot_guide.md L202-213. The live oracle confirmed this layout
    2026-04-24 against BINANCE-ETHUSDT-29MAY2026.

    The bytes32 ABI-return packs the FIndex struct in the UPPER 26 bytes
    (big-endian), leaving the bottom 6 bytes as zero padding:

        bytes32 layout (MSB → LSB):
          bytes [0..4):   fTime         — uint32, unix timestamp
          bytes [4..18):  floatingIndex — int112, 1e18 precision, SIGN-EXTENDED
          bytes [18..26): feeIndex      — uint64
          bytes [26..32): zero padding

    Decode via `val256 >> 48` (discard 6-byte zero pad) → val208, then
    extract fields from top bits of val208.

    NOTE: RESEARCH.md §Pattern 8 used `raw[-26:]` (bottom 26 bytes) which is
    INCORRECT — it reads the zero padding as data. The boros_bot_guide.md L206
    `val >> 48` is authoritative and confirmed live. See docs/samples/
    markets-schema-notes.md for the A5 reconciliation.

    Args:
        raw: 32-byte payload from getLatestFIndex(). Must be exactly 32 bytes.

    Returns:
        dict with keys: fTime (int), floatingIndex (int, signed), feeIndex (int)

    Raises:
        ValueError: if len(raw) != 32.
        FIndexDecodeError: if |floatingIndex| >= 2^110 (T-01-09-02 sanity bound).
    """
    if len(raw) != 32:
        raise ValueError(f"fIndex payload must be 32 bytes, got {len(raw)}")

    # Discard the 6-byte zero-padding at the bottom; retain the upper 208 bits.
    # boros_bot_guide.md L206: `val208 = val >> 48`
    val256 = int.from_bytes(raw, "big")
    val208 = val256 >> 48

    # Unpack fields per the bit layout.
    fTime = (val208 >> 176) & ((1 << 32) - 1)

    floatingIndex = (val208 >> 64) & ((1 << 112) - 1)
    # int112 sign extension: if MSB of 112-bit slot is set, negate.
    if floatingIndex >= (1 << 111):
        floatingIndex -= 1 << 112  # two's complement

    feeIndex = val208 & ((1 << 64) - 1)

    # Sanity bounds — T-01-09-02 threat mitigation.
    # Values >= 2^110 indicate an off-by-one or wrong-endian decode.
    if abs(floatingIndex) >= (1 << 110):
        raise FIndexDecodeError(
            f"floatingIndex={floatingIndex} exceeds 2^110; likely off-by-one or wrong-endian decode. "
            f"fTime={fTime}, feeIndex={feeIndex}"
        )

    return {"fTime": fTime, "floatingIndex": floatingIndex, "feeIndex": feeIndex}


# ── Display helper ─────────────────────────────────────────────────────────────


def fIndex_display(floatingIndex: int, scale: float) -> float:
    """Convert raw floatingIndex to display value.

    Per RESEARCH.md §Pattern 8 line 1021:
        fIndex_display = 10000 + floatingIndex / SCALE

    SCALE is per-market (≈ 5.591e12 for Binance ETHUSDT 29-May-2026 per research).
    Two data points (clo_lower, clo_upper) + two fIndex samples resolve SCALE per
    market — see 01-11 SCALE calibration plan.

    Args:
        floatingIndex: Decoded int112 floatingIndex_raw from fIndexOracle.
        scale: Per-market SCALE calibration constant (float).

    Returns:
        float: fIndex in display units (centered around 10000).
    """
    return 10000.0 + floatingIndex / scale


# ── FIndexReader ───────────────────────────────────────────────────────────────


@dataclass
class FIndexReader:
    """Async reader for a single fIndexOracle contract with TTL cache.

    Caches the decoded result for ``ttl_s`` seconds (default from
    config.data.chain_time_cache_ttl_s = 1.0 s). Sub-TTL duplicate calls do NOT
    hit the RPC — important because the poller calls this on every poll cycle
    (every 30 s by default, which is well above the TTL).

    Args:
        w3: AsyncWeb3 instance (from make_arbitrum_rpc).
        oracle_address: Arbitrum contract address for the per-market fIndexOracle.
        ttl_s: Cache TTL in seconds. Default 1.0 (from config.data.chain_time_cache_ttl_s).
    """

    w3: AsyncWeb3  # type: ignore[type-arg]
    oracle_address: str
    ttl_s: float = 1.0
    _cache: dict[str, int] | None = field(default=None, init=False, repr=False)
    _ts: float = field(default=0.0, init=False, repr=False)

    def _contract(self) -> Any:
        """Return the web3 contract instance (created fresh each call — stateless)."""
        # web3.py contract() requires a ChecksumAddress; to_checksum_address normalises
        # the hex string regardless of case — T-01-09-02 safe (no truncation).
        addr = AsyncWeb3.to_checksum_address(self.oracle_address)
        return self.w3.eth.contract(address=addr, abi=FINDEX_ABI)

    async def get_latest_fIndex(self) -> dict[str, int]:
        """Fetch and decode the latest fIndex payload.

        Returns the cached result if within TTL. On cache miss, calls
        getLatestFIndex() via eth_call and decodes the bytes32 payload.

        Returns:
            dict: {"fTime": int, "floatingIndex": int, "feeIndex": int}

        Raises:
            FIndexDecodeError: if decoded values fail sanity bounds (T-01-09-02).
            web3 exceptions: on RPC failure (caller should catch and log).
        """
        now = time.monotonic()
        if self._cache is not None and (now - self._ts) < self.ttl_s:
            return self._cache
        raw: bytes = await self._contract().functions.getLatestFIndex().call()
        result = decode_findex_bytes(raw)
        self._cache = result
        self._ts = now
        log.debug(
            "findex_reader.refreshed",
            oracle_address=self.oracle_address,
            fTime=result["fTime"],
        )
        return result

    async def latest_annualized_rate(self) -> int:
        """Return the latest annualized rate from the oracle.

        Returns:
            int: 1e18-precision signed int. Divide by 1e18 for APR float.
                 Used by DATA-09 economics gate and SAFE-02 oracle staleness check.
        """
        return await self._contract().functions.latestAnnualizedRate().call()  # type: ignore[no-any-return]
