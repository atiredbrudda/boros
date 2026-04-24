"""Tests for MarketsPoller (DATA-06).

Tests verify:
  - First poll writes clo_history rows with f_index_raw populated
  - Second poll with same data writes 0 additional rows (change-only)
  - CLO change triggers new row
  - fIndex change triggers new row
  - fIndex decode failure writes row with f_index_raw=NULL
  - 5xx HTTP error triggers exponential-backoff retry, succeeds on second call

Uses httpx.MockTransport to stub the REST client.
Uses tmp SQLite + Alembic migration for real clo_history table.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "markets_response_fixture.json"

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_transport(payloads: list[bytes | int]) -> httpx.MockTransport:
    """Build an httpx.MockTransport that returns each payload in sequence.

    Each item in `payloads` is either:
      - bytes: returned as HTTP 200 with that body
      - int: returned as HTTP {int} with empty body
    """
    calls = iter(payloads)

    def handler(request: httpx.Request) -> httpx.Response:
        item = next(calls)
        if isinstance(item, int):
            return httpx.Response(item)
        return httpx.Response(200, content=item)

    return httpx.MockTransport(handler)


def _make_findex_reader(floatingIndex: int = 123_456_789_000_000_000) -> Any:
    """Create a stub FIndexReader that returns a fixed floatingIndex."""
    reader = MagicMock()
    reader.get_latest_fIndex = AsyncMock(
        return_value={"fTime": 1776996232, "floatingIndex": floatingIndex, "feeIndex": 987654321}
    )
    return reader


def _init_db(sqlite_path: Path) -> None:
    """Apply the 0001_initial_8_tables Alembic migration to create clo_history table."""
    from alembic import command
    from alembic.config import Config

    from boros_brain.state.db import open_connection

    # Pre-create file with WAL + FKs (mirrors production open_connection contract).
    with open_connection(sqlite_path):
        pass

    alembic_ini = Path(__file__).resolve().parents[1] / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_ini.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{sqlite_path}")
    command.upgrade(cfg, "head")


def _build_config(sqlite_path: Path) -> Any:
    """Build a minimal BotConfig with the given SQLite path."""
    from boros_brain.config.schema import BotConfig

    return BotConfig.model_validate(
        {
            "mode": "backtest",
            "strategy_version": "v0.5.0",
            "market_id": "BINANCE-ETHUSDT-29MAY2026",
            "side": "short",
            "root_wallet_address": "0xTBD",
            "agent_wallet_address": "0xTBD",
            "data": {
                "rpc_url_arbitrum": "https://arb1.arbitrum.io/rpc",
            },
            "infra": {
                "sqlite_path": str(sqlite_path),
            },
        }
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_markets_poller_writes_clo_history_on_first_poll(tmp_path: Path) -> None:
    """First poll writes clo_history rows for both markets with f_index_raw populated."""
    from boros_brain.data.poller.markets_poller import MarketsPoller

    sqlite_path = tmp_path / "state.sqlite"
    _init_db(sqlite_path)
    config = _build_config(sqlite_path)

    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_data = json.loads(fixture_bytes)
    eth_symbol = fixture_data["results"][0]["imData"]["symbol"]
    btc_symbol = fixture_data["results"][1]["imData"]["symbol"]

    findex_eth = _make_findex_reader(floatingIndex=111_000_000_000_000_000)
    findex_btc = _make_findex_reader(floatingIndex=222_000_000_000_000_000)

    transport = _make_transport([fixture_bytes])
    client = httpx.AsyncClient(transport=transport, base_url="http://test")

    findex_readers = {eth_symbol: findex_eth, btc_symbol: findex_btc}
    poller = MarketsPoller(config, client, run_id="test-run-001", findex_readers=findex_readers)

    # Stub chain time
    from unittest.mock import patch

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996232)):
        written = await poller.tick()

    assert written == 2, f"Expected 2 rows written, got {written}"

    conn = sqlite3.connect(str(sqlite_path))
    rows = conn.execute("SELECT market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw FROM clo_history").fetchall()
    conn.close()

    assert len(rows) == 2
    row_dict = {r[0]: r for r in rows}
    assert eth_symbol in row_dict
    assert btc_symbol in row_dict
    # f_index_raw must be the stubbed floatingIndex value
    assert row_dict[eth_symbol][3] == 111_000_000_000_000_000
    assert row_dict[btc_symbol][3] == 222_000_000_000_000_000


@pytest.mark.asyncio
async def test_markets_poller_skips_write_when_unchanged(tmp_path: Path) -> None:
    """Second poll with same fixture + same fIndex writes 0 additional rows."""
    from boros_brain.data.poller.markets_poller import MarketsPoller

    sqlite_path = tmp_path / "state.sqlite"
    _init_db(sqlite_path)
    config = _build_config(sqlite_path)

    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_data = json.loads(fixture_bytes)
    eth_symbol = fixture_data["results"][0]["imData"]["symbol"]
    btc_symbol = fixture_data["results"][1]["imData"]["symbol"]

    findex_eth = _make_findex_reader(floatingIndex=111_000_000_000_000_000)
    findex_btc = _make_findex_reader(floatingIndex=222_000_000_000_000_000)
    findex_readers = {eth_symbol: findex_eth, btc_symbol: findex_btc}

    # Return same fixture twice
    transport = _make_transport([fixture_bytes, fixture_bytes])
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    poller = MarketsPoller(config, client, run_id="test-run-002", findex_readers=findex_readers)

    from unittest.mock import patch

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996232)):
        first = await poller.tick()
    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996262)):
        second = await poller.tick()

    assert first == 2
    assert second == 0, f"Expected 0 rows on second unchanged poll, got {second}"


@pytest.mark.asyncio
async def test_markets_poller_writes_on_clo_change(tmp_path: Path) -> None:
    """When cloLowerThresh changes for one market on second poll, only that market writes."""
    from boros_brain.data.poller.markets_poller import MarketsPoller

    sqlite_path = tmp_path / "state.sqlite"
    _init_db(sqlite_path)
    config = _build_config(sqlite_path)

    fixture_data = json.loads(FIXTURE_PATH.read_bytes())
    eth_symbol = fixture_data["results"][0]["imData"]["symbol"]
    btc_symbol = fixture_data["results"][1]["imData"]["symbol"]

    # Second fixture: bump ETH cloLowerThresh by 1
    fixture_data2 = json.loads(FIXTURE_PATH.read_bytes())
    original_clo_lower = fixture_data2["results"][0]["config"]["cloLowerThresh"]
    fixture_data2["results"][0]["config"]["cloLowerThresh"] = original_clo_lower + 1
    fixture2_bytes = json.dumps(fixture_data2).encode()

    findex_eth = _make_findex_reader(floatingIndex=111_000_000_000_000_000)
    findex_btc = _make_findex_reader(floatingIndex=222_000_000_000_000_000)
    findex_readers = {eth_symbol: findex_eth, btc_symbol: findex_btc}

    transport = _make_transport([FIXTURE_PATH.read_bytes(), fixture2_bytes])
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    poller = MarketsPoller(config, client, run_id="test-run-003", findex_readers=findex_readers)

    from unittest.mock import patch

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996232)):
        first = await poller.tick()
    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996262)):
        second = await poller.tick()

    assert first == 2
    assert second == 1, f"Expected 1 row on CLO change poll, got {second}"

    # Verify the written row has the updated clo_lower_thresh
    conn = sqlite3.connect(str(sqlite_path))
    rows = conn.execute("SELECT market_id, clo_lower_thresh FROM clo_history ORDER BY snapshot_ts").fetchall()
    conn.close()

    # Should have 3 total rows: 2 from first poll + 1 from second (ETH changed)
    assert len(rows) == 3
    updated_rows = [r for r in rows if r[0] == eth_symbol]
    assert updated_rows[-1][1] == float(original_clo_lower + 1)


@pytest.mark.asyncio
async def test_markets_poller_writes_on_findex_change(tmp_path: Path) -> None:
    """When fIndex changes for one market on second poll (CLO unchanged), that market writes."""
    from boros_brain.data.poller.markets_poller import MarketsPoller

    sqlite_path = tmp_path / "state.sqlite"
    _init_db(sqlite_path)
    config = _build_config(sqlite_path)

    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_data = json.loads(fixture_bytes)
    eth_symbol = fixture_data["results"][0]["imData"]["symbol"]
    btc_symbol = fixture_data["results"][1]["imData"]["symbol"]

    findex_eth_first = _make_findex_reader(floatingIndex=111_000_000_000_000_000)
    findex_eth_second = _make_findex_reader(floatingIndex=999_000_000_000_000_000)
    findex_btc = _make_findex_reader(floatingIndex=222_000_000_000_000_000)

    # First poll uses eth_first; second poll replaces eth reader
    transport = _make_transport([fixture_bytes, fixture_bytes])
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    findex_readers_first = {eth_symbol: findex_eth_first, btc_symbol: findex_btc}
    poller = MarketsPoller(config, client, run_id="test-run-004", findex_readers=findex_readers_first)

    from unittest.mock import patch

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996232)):
        first = await poller.tick()

    # Replace ETH findex reader for second poll
    poller._findex_readers[eth_symbol] = findex_eth_second

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996262)):
        second = await poller.tick()

    assert first == 2
    assert second == 1, f"Expected 1 row written on fIndex change, got {second}"


@pytest.mark.asyncio
async def test_markets_poller_findex_decode_failure_records_null(tmp_path: Path) -> None:
    """When FIndexReader raises, the row is still written with f_index_raw=NULL."""
    from boros_brain.data.poller.markets_poller import MarketsPoller

    sqlite_path = tmp_path / "state.sqlite"
    _init_db(sqlite_path)
    config = _build_config(sqlite_path)

    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_data = json.loads(fixture_bytes)
    eth_symbol = fixture_data["results"][0]["imData"]["symbol"]
    btc_symbol = fixture_data["results"][1]["imData"]["symbol"]

    # ETH reader always raises
    findex_eth_bad = MagicMock()
    findex_eth_bad.get_latest_fIndex = AsyncMock(side_effect=RuntimeError("RPC timeout"))
    findex_btc = _make_findex_reader(floatingIndex=222_000_000_000_000_000)
    findex_readers = {eth_symbol: findex_eth_bad, btc_symbol: findex_btc}

    transport = _make_transport([fixture_bytes])
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    poller = MarketsPoller(config, client, run_id="test-run-005", findex_readers=findex_readers)

    from unittest.mock import patch

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996232)):
        written = await poller.tick()

    # Both markets must still be written (2 rows)
    assert written == 2

    conn = sqlite3.connect(str(sqlite_path))
    rows = conn.execute("SELECT market_id, f_index_raw FROM clo_history").fetchall()
    conn.close()

    row_dict = {r[0]: r[1] for r in rows}
    assert row_dict[eth_symbol] is None, f"ETH f_index_raw must be NULL on decode failure, got {row_dict[eth_symbol]}"
    assert row_dict[btc_symbol] == 222_000_000_000_000_000


@pytest.mark.asyncio
async def test_markets_poller_backs_off_on_5xx(tmp_path: Path) -> None:
    """500 on first call triggers backoff + retry; second call (200) writes rows."""
    from boros_brain.data.poller.markets_poller import MarketsPoller

    sqlite_path = tmp_path / "state.sqlite"
    _init_db(sqlite_path)
    config = _build_config(sqlite_path)

    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_data = json.loads(fixture_bytes)
    eth_symbol = fixture_data["results"][0]["imData"]["symbol"]
    btc_symbol = fixture_data["results"][1]["imData"]["symbol"]

    findex_eth = _make_findex_reader(floatingIndex=111_000_000_000_000_000)
    findex_btc = _make_findex_reader(floatingIndex=222_000_000_000_000_000)
    findex_readers = {eth_symbol: findex_eth, btc_symbol: findex_btc}

    # First response: 500, then 200 with fixture
    transport = _make_transport([500, fixture_bytes])
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    # Use small backoff to keep test fast
    poller = MarketsPoller(config, client, run_id="test-run-006", findex_readers=findex_readers, backoff_base_s=0.01)

    from unittest.mock import patch

    with patch("boros_brain.data.poller.markets_poller.now_cached", AsyncMock(return_value=1776996232)):
        written = await poller.tick()

    assert written == 2, f"Expected 2 rows after 5xx+retry, got {written}"
