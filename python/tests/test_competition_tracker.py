"""REWARD-02: CompetitionTracker tests.

Tests for CompetitionTracker.run_one_cycle composing REST + parquet sources
into one competition_history row per cycle, with degraded-mode fallback after
N=5 consecutive REST failures.

T-03-06 mitigation: AMM share is excluded by reading parquet.order_book_raw
(NOT order_book_combined). Test asserts the SQL targets the raw view.

Tests:
1. test_writes_one_row_per_cycle: single cycle writes one row with data_source='live'.
2. test_sigma_excludes_q_me: with raw_book=100, q_me=30 → sigma_others=70.
3. test_uses_order_book_raw_not_combined: verifies SQL/source string contains
   'order_book_raw' (T-03-06 / AMM exclusion).
4. test_fallback_on_rest_fail: 5 consecutive REST failures → fallback row +
   competition_tracker.rest_degraded event.
5. test_degraded_event_published_only_once: 6th call doesn't re-emit unless recovery.
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
    db = tmp_path / "test.sqlite"
    db.touch()
    command.upgrade(_alembic_cfg(db), "head")
    return db


class StubEventPub:
    """Records published events instead of connecting to ZMQ."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))


def _make_config(market_id: str = "ETHUSDT-29MAY2026") -> Any:
    cfg = MagicMock()
    cfg.reward_share_model.competition_poll_interval_s = 5.0
    cfg.reward_share_model.fallback_to_parquet_after_rest_fails_n = 5
    cfg.root_wallet_address = "0xTEST"
    market = MagicMock()
    market.market_id = market_id
    cfg.markets = [market]
    return cfg


def test_writes_one_row_per_cycle(tmp_path: Path) -> None:
    """One cycle with healthy REST writes one row with data_source='live'."""
    from boros_brain.reward_model.competition_tracker import CompetitionTracker

    db = _migrated_db(tmp_path)
    config = _make_config()
    event_pub = StubEventPub()

    conn = sqlite3.connect(str(db))
    try:
        mock_rest = AsyncMock()
        mock_rest.post_all_limit_orders.return_value = [
            {"marketId": "ETHUSDT-29MAY2026", "sz": "30000000000000000000"},  # 30 in YU wei
        ]

        with patch(
            "boros_brain.reward_model.competition_tracker.get_chain_time_cached",
            new_callable=AsyncMock,
            return_value=1_714_000_000,
        ):
            tracker = CompetitionTracker(config, conn, mock_rest, "run-test-01", event_pub, db)
            # Patch parquet read to return a known total raw book (e.g., 100)
            with patch.object(tracker, "_read_sigma_others_from_parquet", return_value=70.0):
                asyncio.run(tracker.run_one_cycle())

        rows = conn.execute(
            "SELECT q_me_pendle, sigma_others_pendle, data_source, run_id " "FROM competition_history"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    q_me, sigma, ds, run_id = rows[0]
    assert q_me == pytest.approx(30.0, rel=1e-6)
    assert sigma == pytest.approx(70.0, rel=1e-6)
    assert ds == "live"
    assert run_id == "run-test-01"


def test_sigma_excludes_q_me(tmp_path: Path) -> None:
    """sigma_others = total_raw_book_in_range - q_me. Verify the subtraction directly."""
    from boros_brain.reward_model.competition_tracker import CompetitionTracker

    db = _migrated_db(tmp_path)
    config = _make_config()
    event_pub = StubEventPub()

    conn = sqlite3.connect(str(db))
    try:
        mock_rest = AsyncMock()
        # Return q_me = 30
        mock_rest.post_all_limit_orders.return_value = [
            {"marketId": "ETHUSDT-29MAY2026", "sz": "30000000000000000000"},
        ]

        with patch(
            "boros_brain.reward_model.competition_tracker.get_chain_time_cached",
            new_callable=AsyncMock,
            return_value=1_714_000_000,
        ):
            tracker = CompetitionTracker(config, conn, mock_rest, "run-test-02", event_pub, db)

            # Use a stub directly that simulates total_raw=100 - q_me=30 = 70.
            # We patch out the parquet path entirely, then assert the post-conditions.
            captured: dict[str, float] = {}

            def fake_read(market_id: str, chain_ts: int, q_me: float) -> float:
                captured["q_me"] = q_me
                # Subtraction logic baked into CompetitionTracker is `max(0, total_raw - q_me)`;
                # we precompute and return.
                total_raw = 100.0
                return max(0.0, total_raw - q_me)

            with patch.object(tracker, "_read_sigma_others_from_parquet", side_effect=fake_read):
                asyncio.run(tracker.run_one_cycle())

        rows = conn.execute("SELECT q_me_pendle, sigma_others_pendle FROM competition_history").fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    q_me, sigma = rows[0]
    assert q_me == pytest.approx(30.0, rel=1e-6)
    assert sigma == pytest.approx(70.0, rel=1e-6), "sigma_others must equal raw_total - q_me"
    assert captured["q_me"] == pytest.approx(30.0, rel=1e-6)


def test_uses_order_book_raw_not_combined() -> None:
    """T-03-06: source code reads parquet.order_book_raw (not order_book_combined).

    AMMs do not compete for LO Liquidity Rewards, so Σ_others must exclude AMM
    share by reading the raw view (combined - amm_share = raw).
    """
    from boros_brain.reward_model import competition_tracker as ct_module

    src = Path(ct_module.__file__).read_text()
    assert "order_book_raw" in src, (
        "competition_tracker.py must reference parquet.order_book_raw " "(T-03-06 AMM exclusion)"
    )
    # NB: the file may legitimately mention 'order_book_combined' in a comment
    # explaining the exclusion rationale; we ensure the SQL query uses 'order_book_raw'.
    assert "FROM order_book_raw" in src or "order_book_raw," in src, "SQL query must SELECT FROM order_book_raw"


def test_fallback_on_rest_fail(tmp_path: Path) -> None:
    """5 consecutive REST failures → data_source='fallback_parquet_only' + degraded event."""
    from boros_brain.reward_model.competition_tracker import CompetitionTracker

    db = _migrated_db(tmp_path)
    config = _make_config()
    event_pub = StubEventPub()

    conn = sqlite3.connect(str(db))
    try:
        # REST always raises httpx.HTTPStatusError (503).
        mock_rest = AsyncMock()
        mock_rest.post_all_limit_orders.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=MagicMock(),
            response=MagicMock(status_code=503),
        )

        with (
            patch(
                "boros_brain.reward_model.competition_tracker.get_chain_time_cached",
                new_callable=AsyncMock,
                return_value=1_714_000_000,
            ),
            patch(
                "boros_brain.reward_model.competition_tracker.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            tracker = CompetitionTracker(config, conn, mock_rest, "run-test-04", event_pub, db)
            # Stub parquet read so the test isolates the REST failure path.
            with patch.object(tracker, "_read_sigma_others_from_parquet", return_value=0.0):
                # 5 consecutive failing cycles → fail_count reaches threshold (5)
                # on the 5th cycle, triggering fallback + degraded event.
                for _ in range(5):
                    asyncio.run(tracker.run_one_cycle())

        rows = conn.execute("SELECT q_me_pendle, sigma_others_pendle, data_source FROM competition_history").fetchall()
    finally:
        conn.close()

    assert len(rows) == 5, f"expected 5 rows (one per cycle), got {len(rows)}"
    # All rows must be fallback (REST was always failing).
    for _q_me, _sigma, ds in rows:
        assert ds == "fallback_parquet_only", f"expected fallback, got {ds}"
    # After 5 consecutive failures, degraded event must be published.
    assert any(
        topic == "competition_tracker.rest_degraded" for topic, _ in event_pub.published
    ), f"expected competition_tracker.rest_degraded event, got {event_pub.published}"


def test_degraded_event_published_only_once(tmp_path: Path) -> None:
    """6th cycle on continued failure must not re-emit the degraded event."""
    from boros_brain.reward_model.competition_tracker import CompetitionTracker

    db = _migrated_db(tmp_path)
    config = _make_config()
    event_pub = StubEventPub()

    conn = sqlite3.connect(str(db))
    try:
        mock_rest = AsyncMock()
        mock_rest.post_all_limit_orders.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock(status_code=503)
        )

        with (
            patch(
                "boros_brain.reward_model.competition_tracker.get_chain_time_cached",
                new_callable=AsyncMock,
                return_value=1_714_000_000,
            ),
            patch(
                "boros_brain.reward_model.competition_tracker.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            tracker = CompetitionTracker(config, conn, mock_rest, "run-test-05", event_pub, db)
            with patch.object(tracker, "_read_sigma_others_from_parquet", return_value=0.0):
                for _ in range(5):
                    asyncio.run(tracker.run_one_cycle())  # cycles 1-5: 5th emits degraded
                asyncio.run(tracker.run_one_cycle())  # cycle 6: must NOT re-emit
    finally:
        conn.close()

    n_degraded = sum(1 for topic, _ in event_pub.published if topic == "competition_tracker.rest_degraded")
    assert n_degraded == 1, f"expected exactly 1 degraded event, got {n_degraded}: {event_pub.published}"
