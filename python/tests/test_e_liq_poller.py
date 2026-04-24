"""DATA-11 E_liq poller tests.

Tests for ELiqPoller + insert_reward_budget_row writer.

T-01-10-02 (no-cache invariant): ELiqPoller must write one row per cycle —
no cross-poll dedup — because E_liq_per_epoch rebalances dynamically per
epoch (PITFALLS §A2 / ARCHITECTURE.md §9 Anti-pattern 4).

T-01-10-03 (backoff on 503): Boros REST 5xx errors must NOT crash the poller
loop. After 5 consecutive failures, the poller logs ERROR and publishes
'poller.e_liq.degraded' ZMQ event.

Test cases:
1. test_insert_reward_budget_row_inserts_one_row
   insert_reward_budget_row() inserts exactly one row with polled_at_utc
   populated (ISO8601) and all fields stored correctly.

2. test_data_source_check_constraint_rejects_invalid
   data_source CHECK constraint rejects values other than 'polled' or
   'synthetic_current'.

3. test_e_liq_poller_no_cache_writes_two_rows
   ELiqPoller.run_one_cycle() called twice with identical JSON returns
   produces TWO rows in reward_budget_history (no cache dedup).

4. test_e_liq_poller_backoff_on_503
   With HTTP 503s on every attempt, poller logs ERROR but does not raise.
   reward_budget_history stays empty. After 5th failure a ZMQ-stub event
   'poller.e_liq.degraded' is published.

5. test_reward_budget_history_schema
   PRAGMA table_info(reward_budget_history) confirms expected columns:
   id, polled_at_utc, chain_ts, market_id, e_liq_per_epoch, long_budget,
   short_budget, run_id, data_source.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def _alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _migrated_db(tmp_path: Path) -> Path:
    """Return path to a fully-migrated SQLite DB."""
    db = tmp_path / "test.sqlite"
    db.touch()
    command.upgrade(_alembic_cfg(db), "head")
    return db


# ── Stub classes ─────────────────────────────────────────────────────────────


class StubEventPub:
    """Records published events instead of connecting to ZMQ."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))


def _make_config(market_id: str = "ETHUSDT-29MAY2026", interval: float = 5.0) -> Any:
    """Minimal config stub with data.e_liq_poll_interval_s and markets list."""
    cfg = MagicMock()
    cfg.data.e_liq_poll_interval_s = interval
    cfg.data.boros_rest_base = "https://api.boros.finance/open-api/v1"
    market = MagicMock()
    market.market_id = market_id
    cfg.markets = [market]
    return cfg


def _market_payload(market_id: str = "ETHUSDT-29MAY2026") -> list[dict]:
    """Minimal /markets response with E_liq fields."""
    return [
        {
            "marketId": market_id,
            "liquidityRewardPerEpoch": "45.7",
            "longBudget": "6.663",
            "shortBudget": "39.05",
        }
    ]


# ── Test 1: insert_reward_budget_row ─────────────────────────────────────────


def test_insert_reward_budget_row_inserts_one_row(tmp_path: Path) -> None:
    """insert_reward_budget_row inserts exactly one row with polled_at_utc populated."""
    db = _migrated_db(tmp_path)
    from boros_brain.state.writers.reward_budget_history import insert_reward_budget_row

    conn = sqlite3.connect(str(db))
    try:
        insert_reward_budget_row(
            conn,
            market_id="ETHUSDT-29MAY2026",
            e_liq_per_epoch=45.7,
            long_budget=6.663,
            short_budget=39.05,
            chain_ts=1_714_000_000,
            run_id="run-test-01",
            data_source="polled",
        )
        rows = conn.execute(
            "SELECT polled_at_utc, chain_ts, market_id, e_liq_per_epoch, long_budget, "
            "short_budget, run_id, data_source FROM reward_budget_history"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    polled_at_utc, chain_ts, market_id, e_liq, long_b, short_b, run_id, data_source = rows[0]
    assert polled_at_utc is not None and len(polled_at_utc) > 10, "polled_at_utc should be ISO8601"
    assert chain_ts == 1_714_000_000
    assert market_id == "ETHUSDT-29MAY2026"
    assert abs(e_liq - 45.7) < 1e-6
    assert abs(long_b - 6.663) < 1e-6
    assert abs(short_b - 39.05) < 1e-6
    assert run_id == "run-test-01"
    assert data_source == "polled"


# ── Test 2: data_source CHECK constraint ──────────────────────────────────────


def test_data_source_check_constraint_rejects_invalid(tmp_path: Path) -> None:
    """data_source CHECK constraint must reject values outside {'polled','synthetic_current'}."""
    db = _migrated_db(tmp_path)
    from boros_brain.state.writers.reward_budget_history import insert_reward_budget_row

    conn = sqlite3.connect(str(db))
    try:
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            insert_reward_budget_row(
                conn,
                market_id="X",
                e_liq_per_epoch=1.0,
                long_budget=0.5,
                short_budget=0.5,
                chain_ts=1,
                run_id="run-x",
                data_source="live",  # type: ignore[arg-type]
            )
    finally:
        conn.close()


# ── Test 3: no-cache invariant ────────────────────────────────────────────────


def test_e_liq_poller_no_cache_writes_two_rows(tmp_path: Path) -> None:
    """ELiqPoller.run_one_cycle() called twice must write TWO rows (no cross-poll caching).

    T-01-10-02 / PITFALLS §A2 / ARCHITECTURE.md §9 Anti-pattern 4:
    E_liq_per_epoch rebalances dynamically; caching across polls produces wrong
    R_apr_on_collateral in DATA-09.
    """
    db = _migrated_db(tmp_path)
    from boros_brain.data.poller.e_liq_poller import ELiqPoller

    config = _make_config()
    event_pub = StubEventPub()
    payload = _market_payload()

    conn = sqlite3.connect(str(db))
    try:
        mock_rest = AsyncMock()
        mock_rest.get_markets.return_value = payload

        with patch(
            "boros_brain.data.poller.e_liq_poller.get_chain_time_cached",
            new_callable=AsyncMock,
            return_value=1_714_000_000,
        ):
            poller = ELiqPoller(config, conn, mock_rest, "run-test-03", event_pub)
            asyncio.run(poller.run_one_cycle())
            asyncio.run(poller.run_one_cycle())

        count = conn.execute("SELECT COUNT(*) FROM reward_budget_history").fetchone()[0]
    finally:
        conn.close()

    assert count == 2, f"Expected 2 rows (no cache), got {count}"


# ── Test 4: backoff on 503 ────────────────────────────────────────────────────


def test_e_liq_poller_backoff_on_503(tmp_path: Path) -> None:
    """With 503s on every attempt, poller must not raise and must publish degraded event.

    T-01-10-03 mitigation: exponential backoff (0.5, 1, 2, 4, 8s), on 5 consecutive
    failures log ERROR + publish 'poller.e_liq.degraded' ZMQ event + continue loop.
    """
    db = _migrated_db(tmp_path)
    from boros_brain.data.poller.e_liq_poller import ELiqPoller

    config = _make_config()
    event_pub = StubEventPub()

    conn = sqlite3.connect(str(db))
    try:
        # REST always raises httpx.HTTPStatusError (503)
        mock_rest = AsyncMock()
        mock_rest.get_markets.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=MagicMock(),
            response=MagicMock(status_code=503),
        )

        poller = ELiqPoller(config, conn, mock_rest, "run-test-04", event_pub)

        # Patch asyncio.sleep to avoid real delays in test
        with patch("boros_brain.data.poller.e_liq_poller.asyncio.sleep", new_callable=AsyncMock):
            # run_one_cycle must not raise even with all retries exhausted
            asyncio.run(poller.run_one_cycle())

        count = conn.execute("SELECT COUNT(*) FROM reward_budget_history").fetchone()[0]
    finally:
        conn.close()

    assert count == 0, "No rows should be written on backoff failure"
    # After 5 consecutive failures the degraded event must be published
    assert any(
        topic == "poller.e_liq.degraded" for topic, _ in event_pub.published
    ), f"Expected 'poller.e_liq.degraded' event, got {event_pub.published}"


# ── Test 5: schema columns ────────────────────────────────────────────────────


def test_reward_budget_history_schema(tmp_path: Path) -> None:
    """PRAGMA table_info confirms expected columns in reward_budget_history."""
    db = _migrated_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(reward_budget_history)").fetchall()}
    finally:
        conn.close()

    expected = {
        "id",
        "polled_at_utc",
        "chain_ts",
        "market_id",
        "e_liq_per_epoch",
        "long_budget",
        "short_budget",
        "run_id",
        "data_source",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"
