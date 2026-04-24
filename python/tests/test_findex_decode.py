"""Pure-function tests for decode_findex_bytes (DATA-07).

Tests the bytes26-in-bytes32 decode math with no RPC dependency.
Covers the int112 sign-extension path (boros_bot_guide.md L202-213).

IMPORTANT: The layout confirmed live against BINANCE-ETHUSDT-29MAY2026 oracle
(2026-04-24) is TOP-bytes-first — data is in the UPPER 26 bytes, zero-padded
at the bottom. Decode via `val256 >> 48` (boros_bot_guide.md L206).

The RESEARCH.md §Pattern 8 `raw[-26:]` approach is WRONG (reads zero pad).

These tests run fully offline — no Arbitrum RPC required.
The live-RPC smoke test is in test_findex_reader.py.
"""

from __future__ import annotations


def _pack(fTime: int, floatingIndex: int, feeIndex: int) -> bytes:
    """Build a 32-byte payload matching the fIndexOracle getLatestFIndex() layout.

    Layout (TOP 26 bytes = 208 bits, bottom 6 bytes = zero pad):
        bytes [0..4):   fTime         — uint32, unix timestamp
        bytes [4..18):  floatingIndex — int112 (two's-complement for negatives)
        bytes [18..26): feeIndex      — uint64
        bytes [26..32): zero padding

    Encodes as: pack val208 into the TOP 26 bytes (shift LEFT 48 bits).
    This matches the oracle's bytes32 ABI encoding.

    Confirmed correct via live oracle BINANCE-ETHUSDT-29MAY2026 2026-04-24.
    """
    fi_raw = floatingIndex & ((1 << 112) - 1)  # two's-complement truncation
    val208 = ((fTime & ((1 << 32) - 1)) << 176) | (fi_raw << 64) | (feeIndex & ((1 << 64) - 1))
    # Place val208 in the TOP 26 bytes of a 32-byte result (6-byte zero pad at bottom)
    val256 = val208 << 48
    return val256.to_bytes(32, "big")


def test_decode_zero_payload() -> None:
    """decode_findex_bytes of 32 zero bytes returns all fields as 0."""
    from boros_brain.data.findex_reader import decode_findex_bytes

    result = decode_findex_bytes(b"\x00" * 32)
    assert result == {"fTime": 0, "floatingIndex": 0, "feeIndex": 0}


def test_decode_known_synthetic_payload() -> None:
    """Round-trip: pack then decode returns the original values exactly."""
    from boros_brain.data.findex_reader import decode_findex_bytes

    fTime = 1754021093
    floatingIndex = 12345 * (10**18)  # positive, within int112 range
    feeIndex = 987654321

    raw = _pack(fTime, floatingIndex, feeIndex)
    assert len(raw) == 32

    result = decode_findex_bytes(raw)
    assert result["fTime"] == fTime
    assert result["floatingIndex"] == floatingIndex
    assert result["feeIndex"] == feeIndex


def test_decode_negative_floatingIndex_sign_extends() -> None:
    """floatingIndex = -1 (all-ones in 112-bit slot) must decode as -1 after sign extension.

    This is the critical int112 sign-extension path from RESEARCH.md §Pattern 8 line 974-976.
    """
    from boros_brain.data.findex_reader import decode_findex_bytes

    raw = _pack(fTime=0, floatingIndex=-1, feeIndex=0)
    result = decode_findex_bytes(raw)
    assert result["floatingIndex"] == -1, f"Expected -1, got {result['floatingIndex']}"


def test_decode_fTime_extraction() -> None:
    """payload with fTime=0xFFFFFFFF and all other fields zero decodes fTime correctly."""
    from boros_brain.data.findex_reader import decode_findex_bytes

    raw = _pack(fTime=0xFFFFFFFF, floatingIndex=0, feeIndex=0)
    result = decode_findex_bytes(raw)
    assert result["fTime"] == 0xFFFFFFFF
    assert result["floatingIndex"] == 0
    assert result["feeIndex"] == 0


def test_decode_rejects_wrong_length() -> None:
    """decode_findex_bytes must raise ValueError for payloads != 32 bytes."""
    import pytest

    from boros_brain.data.findex_reader import decode_findex_bytes

    with pytest.raises(ValueError, match="32 bytes"):
        decode_findex_bytes(b"\x00" * 16)

    with pytest.raises(ValueError, match="32 bytes"):
        decode_findex_bytes(b"\x00" * 31)

    with pytest.raises(ValueError, match="32 bytes"):
        decode_findex_bytes(b"\x00" * 33)
