"""Idempotency + ZIP safety tests for scripts/fetch_historical_data.py.

Test functions:
  - test_fetcher_skips_already_fetched_files: skip rule on matching (url, sha256, length) triple
  - test_fetcher_rejects_zip_path_traversal: path traversal blocked (CVE-2007-4559 class)
  - test_fetcher_rejects_zip_bomb: MAX_DECOMPRESSED_BYTES cap halts with clear ValueError
  - test_fetcher_atomic_write_round_trip: _atomic_write creates parent dirs + file equals input bytes

[[boros-historical-data-archive-url-pattern]]
[[run-manifest-writer]]
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig


def test_fetcher_skips_already_fetched_files(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running the fetcher with a populated manifest + matching local files is a no-op.

    Pattern 2 from PATTERNS.md §test_fetch_historical_data_idempotency.py:
    _record_fetched + _is_already_fetched round-trip; sha256 tamper forces refetch.
    """
    from scripts.fetch_historical_data import _is_already_fetched, _record_fetched

    manifest: dict = {"fetched": []}
    local = tmp_path / "ndjson" / "market-trades" / "TEST" / "2026-04.ndjson"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(b'{"eventIndex":1}\n')

    sha = hashlib.sha256(local.read_bytes()).hexdigest()
    _record_fetched(
        manifest,
        url="https://example.invalid/foo.ndjson",
        local_path=local,
        content_length=local.stat().st_size,
        sha256=sha,
        run_id="test-run-001",
    )

    # Same triple → already fetched → skip
    assert _is_already_fetched(manifest, url="https://example.invalid/foo.ndjson", local_path=local)

    # Tamper with local file → sha256 mismatch → NOT already fetched (refetch required)
    local.write_bytes(b'{"eventIndex":2}\n')
    assert not _is_already_fetched(manifest, url="https://example.invalid/foo.ndjson", local_path=local)


def test_fetcher_rejects_zip_path_traversal(tmp_path: Path) -> None:
    """ZIP entry with '../' path components raises ValueError('path traversal blocked').

    Builds a malicious ZIP with an entry like '../../escape.ndjson' and asserts
    the fetcher's extract step rejects it (CVE-2007-4559 historical class).
    """
    from scripts.fetch_historical_data import _safe_extract_zip

    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../../escape.ndjson", b"hostile")

    with pytest.raises(ValueError, match="path traversal blocked"):
        _safe_extract_zip(bad_zip, out_root=tmp_path / "ndjson")


def test_fetcher_rejects_zip_bomb(tmp_path: Path) -> None:
    """ZIP whose decompressed size exceeds MAX_DECOMPRESSED_BYTES halts with a clear error.

    Monkeypatches MAX_DECOMPRESSED_BYTES to 64 bytes so the test runs without
    actually inflating a 10 GB archive. The ValueError message must match the
    grep-auditable pattern: 'zip bomb|exceeds.*cap|max.*decompressed'.
    """
    import scripts.fetch_historical_data as fetcher_mod
    from scripts.fetch_historical_data import _safe_extract_zip

    bomb = tmp_path / "bomb.zip"
    original_cap = fetcher_mod.MAX_DECOMPRESSED_BYTES
    try:
        fetcher_mod.MAX_DECOMPRESSED_BYTES = 64  # bytes — tiny cap for testing
        with zipfile.ZipFile(bomb, "w") as zf:
            zf.writestr("payload.ndjson", b"x" * 1024)  # 1 KiB > 64 B cap

        with pytest.raises(ValueError, match="zip bomb|exceeds.*cap|max.*decompressed"):
            _safe_extract_zip(bomb, out_root=tmp_path / "ndjson")
    finally:
        fetcher_mod.MAX_DECOMPRESSED_BYTES = original_cap


def test_fetcher_atomic_write_round_trip(tmp_path: Path) -> None:
    """_atomic_write creates parent directories and resulting file equals input bytes.

    Verifies that atomic write via tmp + os.replace works even when parent dirs
    don't yet exist — the fetcher's first write to a new market/kind/period path.
    """
    from scripts.fetch_historical_data import _atomic_write

    # Parent does NOT exist yet — _atomic_write must create it
    target = tmp_path / "ndjson" / "market-trades" / "NEW-MARKET" / "2026-04.ndjson"
    assert not target.parent.exists(), "pre-condition: parent dir should not exist"

    data = b'{"eventIndex":42}\n{"eventIndex":43}\n'
    _atomic_write(target, data)

    assert target.exists(), f"target not written: {target}"
    assert target.read_bytes() == data, "file content mismatch"
