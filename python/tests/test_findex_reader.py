"""Tests for FIndexReader (DATA-07).

Covers TTL caching, annualized rate return type, and a skip-on-CI live-RPC
smoke test that validates the bytes26 math against real mainnet data.

The pure-function decode tests are in test_findex_decode.py.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest

# ── Helpers — fake web3 hierarchy ────────────────────────────────────────────


def _pack(fTime: int, floatingIndex: int, feeIndex: int) -> bytes:
    """Build a 32-byte fIndex payload matching the live oracle encoding.

    Data is in the TOP 26 bytes; bottom 6 bytes are zero padding.
    Encodes via: pack val208, then shift LEFT 48 bits.
    Confirmed correct against BINANCE-ETHUSDT-29MAY2026 oracle 2026-04-24.
    """
    fi_raw = floatingIndex & ((1 << 112) - 1)
    val208 = ((fTime & ((1 << 32) - 1)) << 176) | (fi_raw << 64) | (feeIndex & ((1 << 64) - 1))
    return (val208 << 48).to_bytes(32, "big")


class _FakeFunctions:
    """Stub for contract.functions — returns canned payloads."""

    def __init__(self, payload: bytes, annualized_rate: int = 50_000_000_000_000_000) -> None:
        self._payload = payload
        self._rate = annualized_rate

    def getLatestFIndex(self) -> Any:
        payload = self._payload

        class _Call:
            async def call(_self) -> bytes:  # noqa: N805
                return payload

        return _Call()

    def latestAnnualizedRate(self) -> Any:
        rate = self._rate

        class _Call:
            async def call(_self) -> int:  # noqa: N805
                return rate

        return _Call()


class _FakeContract:
    def __init__(self, payload: bytes, annualized_rate: int = 50_000_000_000_000_000) -> None:
        self.functions = _FakeFunctions(payload, annualized_rate)


class _FakeEth:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def contract(self, address: Any, abi: Any) -> _FakeContract:
        return _FakeContract(self._payload)


class _FakeW3:
    def __init__(self, payload: bytes) -> None:
        self.eth = _FakeEth(payload)

    @staticmethod
    def to_checksum_address(addr: str) -> str:
        return addr  # passthrough for tests


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_findex_reader_returns_parsed_dict() -> None:
    """FIndexReader.get_latest_fIndex() decodes a crafted bytes32 payload correctly."""
    from boros_brain.data.findex_reader import FIndexReader

    fTime = 1776996232
    floatingIndex = 5_591_000_000_000_000  # ~1e15
    feeIndex = 42_000_000_000

    payload = _pack(fTime, floatingIndex, feeIndex)
    w3 = _FakeW3(payload)

    reader = FIndexReader(w3=w3, oracle_address="0x1950dc94e3063267049482f075af72107eb79352", ttl_s=1.0)  # type: ignore[arg-type]
    result = await reader.get_latest_fIndex()

    assert result["fTime"] == fTime
    assert result["floatingIndex"] == floatingIndex
    assert result["feeIndex"] == feeIndex


@pytest.mark.asyncio
async def test_findex_reader_caches_within_ttl() -> None:
    """Two calls within TTL window must produce exactly one RPC call."""
    from boros_brain.data.findex_reader import FIndexReader

    payload = _pack(fTime=1776996232, floatingIndex=123, feeIndex=456)

    call_count = 0
    original_payload = payload

    class _CountingFunctions(_FakeFunctions):
        def getLatestFIndex(self) -> Any:
            nonlocal call_count

            class _Call:
                async def call(_self) -> bytes:  # noqa: N805
                    nonlocal call_count
                    call_count += 1
                    return original_payload

            return _Call()

    class _CountingContract:
        def __init__(self) -> None:
            self.functions = _CountingFunctions(original_payload)

    class _CountingEth:
        def contract(self, address: Any, abi: Any) -> _CountingContract:
            return _CountingContract()

    class _CountingW3:
        def __init__(self) -> None:
            self.eth = _CountingEth()

        @staticmethod
        def to_checksum_address(addr: str) -> str:
            return addr

    reader = FIndexReader(w3=_CountingW3(), oracle_address="0x1950dc94e3063267049482f075af72107eb79352", ttl_s=1.0)  # type: ignore[arg-type]

    # Two calls within the 1s TTL
    await reader.get_latest_fIndex()
    await reader.get_latest_fIndex()

    assert call_count == 1, f"Expected 1 RPC call (cache hit on 2nd), got {call_count}"


@pytest.mark.asyncio
async def test_findex_reader_refreshes_after_ttl() -> None:
    """Two calls spaced > TTL seconds apart must produce two RPC calls."""
    from boros_brain.data.findex_reader import FIndexReader

    payload = _pack(fTime=1776996232, floatingIndex=123, feeIndex=456)
    call_count = 0
    original_payload = payload

    class _CountingFunctions2(_FakeFunctions):
        def getLatestFIndex(self) -> Any:
            nonlocal call_count

            class _Call:
                async def call(_self) -> bytes:  # noqa: N805
                    nonlocal call_count
                    call_count += 1
                    return original_payload

            return _Call()

    class _CountingContract2:
        def __init__(self) -> None:
            self.functions = _CountingFunctions2(original_payload)

    class _CountingEth2:
        def contract(self, address: Any, abi: Any) -> _CountingContract2:
            return _CountingContract2()

    class _CountingW32:
        def __init__(self) -> None:
            self.eth = _CountingEth2()

        @staticmethod
        def to_checksum_address(addr: str) -> str:
            return addr

    # Very short TTL so we can expire it with a brief sleep
    reader = FIndexReader(w3=_CountingW32(), oracle_address="0x1950dc94e3063267049482f075af72107eb79352", ttl_s=0.05)  # type: ignore[arg-type]

    await reader.get_latest_fIndex()
    await asyncio.sleep(0.1)  # exceed TTL
    await reader.get_latest_fIndex()

    assert call_count == 2, f"Expected 2 RPC calls (TTL expired), got {call_count}"


@pytest.mark.asyncio
async def test_findex_reader_annualized_rate_returns_int() -> None:
    """latest_annualized_rate() must return an int (1e18-precision signed)."""
    from boros_brain.data.findex_reader import FIndexReader

    payload = _pack(fTime=0, floatingIndex=0, feeIndex=0)
    w3 = _FakeW3(payload)

    reader = FIndexReader(w3=w3, oracle_address="0x1950dc94e3063267049482f075af72107eb79352", ttl_s=1.0)  # type: ignore[arg-type]
    rate = await reader.latest_annualized_rate()

    assert isinstance(rate, int), f"Expected int, got {type(rate)}"
    # 5% APR at 1e18 precision
    assert rate == 50_000_000_000_000_000


# ── Live RPC smoke test — skipped on CI ──────────────────────────────────────


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="live RPC — run manually")
@pytest.mark.asyncio
async def test_findex_decode_from_live_rpc() -> None:
    """Smoke test: call getLatestFIndex() on the Binance ETHUSDT 29-May-2026 oracle,
    decode, and assert plausible values.

    Run locally with:
        CI= uv run pytest python/tests/test_findex_reader.py::test_findex_decode_from_live_rpc -x -s

    This confirms the bytes26 math matches real mainnet data (T-01-09-02 calibration).
    """
    from web3 import AsyncWeb3
    from web3.providers.rpc import AsyncHTTPProvider

    from boros_brain.data.findex_reader import KNOWN_ORACLES, FIndexReader

    w3 = AsyncWeb3(AsyncHTTPProvider("https://arb1.arbitrum.io/rpc"))
    oracle_addr = KNOWN_ORACLES["BINANCE-ETHUSDT-29MAY2026"]
    reader = FIndexReader(w3=w3, oracle_address=oracle_addr, ttl_s=1.0)

    result = await reader.get_latest_fIndex()

    # fTime must be a positive unix timestamp and not too stale.
    # The oracle updates on a cadence tied to the funding period (paymentPeriod=3600s
    # per the /markets API). Allow up to 24 hours drift for the smoke test — SAFE-02
    # oracle staleness breaker (fTime > 0.7 × maxUpdateDelay) is the production guard.
    assert result["fTime"] > 0, "fTime must be > 0"
    assert (
        abs(time.time() - result["fTime"]) < 86400
    ), f"fTime={result['fTime']} is more than 24 hours from wall clock — oracle likely stale or decode error"

    # feeIndex must be positive (non-zero fee)
    assert result["feeIndex"] > 0, f"feeIndex must be > 0, got {result['feeIndex']}"

    # floatingIndex must be within the 2^110 sanity bound
    assert abs(result["floatingIndex"]) < (
        1 << 110
    ), f"|floatingIndex|={abs(result['floatingIndex'])} exceeds 2^110 — decode error"
