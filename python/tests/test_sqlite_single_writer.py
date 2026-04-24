"""INFRA-03 / PROTO-02 — single-writer-per-table discipline, proven by tests.

The primary mechanical enforcer is `scripts/sqlite_writer_lint.py` (tested
separately in `scripts/tests/test_sqlite_writer_lint.py`). This module exercises
the writer API itself — one round-trip per brain-owned table and a sanity check
that the hands-owned tables' Python writers are `TEST_ONLY`-gated.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from boros_brain.state import writers
from boros_brain.state.db import open_connection

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def _upgrade(db_path: Path) -> None:
    # Touch the DB via open_connection first so perms + WAL are established.
    with open_connection(db_path):
        pass
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_decisions_round_trip(tmp_path: Path) -> None:
    """brain-owned writer inserts a decision; raw SELECT reads the same row back."""
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.decisions.insert_decision(
            conn,
            decision_id="d-01",
            ts_ms=1_714_000_000_000,
            run_id="run-abc",
            market_id="ETHUSDT-29MAY2026",
            decision="hold",
            ev_hold=0.0123,
            p_fill=0.04,
            e_loss=0.01,
            r_share=0.05,
            reason="below-threshold",
        )
        row = conn.execute(
            "SELECT decision_id, ts_ms, run_id, market_id, decision, ev_hold, p_fill, e_loss, r_share, reason "
            "FROM decisions WHERE decision_id='d-01'"
        ).fetchone()
    assert row == (
        "d-01",
        1_714_000_000_000,
        "run-abc",
        "ETHUSDT-29MAY2026",
        "hold",
        0.0123,
        0.04,
        0.01,
        0.05,
        "below-threshold",
    )


def test_queue_positions_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.queue_positions.insert_queue_position(
            conn,
            snapshot_ts=1_714_000_000,
            market_id="ETHUSDT-29MAY2026",
            side="long",
            tick=9600,
            our_order_id="ord-1",
            queue_ahead_size_wei="1000000000000000000",
        )
        row = conn.execute("SELECT our_order_id, tick, side FROM queue_positions").fetchone()
    assert row == ("ord-1", 9600, "long")


def test_run_manifests_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.run_manifests.insert_run_manifest(
            conn,
            run_id="run-parent",
            parent_run_id=None,
            started_at_iso="2026-04-23T23:50:00Z",
            mode="paper",
            strategy_version="v0.5.0",
            git_sha="deadbeef",
            git_dirty=0,
            market_id="ETHUSDT-29MAY2026",
            side="long",
            wallet_address_hash="0xhashed",
            config_json='{"k": 1}',
        )
        row = conn.execute("SELECT run_id, parent_run_id, mode, strategy_version FROM run_manifests").fetchone()
    assert row == ("run-parent", None, "paper", "v0.5.0")


def test_epoch_rewards_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.epoch_rewards.insert_epoch_reward(
            conn,
            epoch_end_ts=1_714_000_000,
            market_id="ETHUSDT-29MAY2026",
            our_accrued_pendle=12.5,
            claimed=0,
            claim_tx_hash=None,
        )
        row = conn.execute("SELECT epoch_end_ts, market_id, our_accrued_pendle, claimed FROM epoch_rewards").fetchone()
    assert row == (1_714_000_000, "ETHUSDT-29MAY2026", 12.5, 0)


def test_clo_history_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.clo_history.insert_clo_snapshot(
            conn,
            snapshot_ts=1_714_000_000,
            market_id="ETHUSDT-29MAY2026",
            clo_lower_thresh=9300.0,
            clo_upper_thresh=9500.0,
            f_index_raw=123_456,
        )
        row = conn.execute("SELECT f_index_raw FROM clo_history").fetchone()
    assert row == (123_456,)


def test_reward_budget_history_round_trip_polled(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.reward_budget_history.insert_reward_budget_row(
            conn,
            market_id="ETHUSDT-29MAY2026",
            e_liq_per_epoch=45.7,
            long_budget=6.663,
            short_budget=39.05,
            chain_ts=1_714_000_000,
            run_id="run-abc",
            data_source="polled",
        )
        row = conn.execute("SELECT data_source, long_budget FROM reward_budget_history").fetchone()
    assert row == ("polled", 6.663)


def test_reward_budget_history_rejects_invalid_data_source(tmp_path: Path) -> None:
    """The writer itself validates `data_source` before SQL runs."""
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        try:
            writers.reward_budget_history.insert_reward_budget_row(
                conn,
                market_id="X",
                e_liq_per_epoch=1.0,
                long_budget=0.5,
                short_budget=0.5,
                chain_ts=1,
                run_id="run-x",
                data_source="invalid",  # type: ignore[arg-type]
            )
        except (ValueError, sqlite3.IntegrityError):
            return
        raise AssertionError("invalid data_source was not rejected")


def test_hands_owned_python_writers_are_test_only(tmp_path: Path) -> None:
    """Python writers for open_orders + tx_receipts exist only for test seeding."""
    assert writers.open_orders.TEST_ONLY is True
    assert writers.tx_receipts.TEST_ONLY is True

    # And the test-only writers still work for integration seeding:
    db = tmp_path / "s.sqlite"
    _upgrade(db)
    with open_connection(db) as conn:
        writers.open_orders.insert_open_order(
            conn,
            order_id="ord-1",
            market_id="ETHUSDT-29MAY2026",
            side="long",
            depth_ticks=50,
            size_wei="1000000000000000000",
            rate=9400,
            status="filling",
            placed_at_ts=1_714_000_000,
            run_id="run-abc",
        )
        row = conn.execute("SELECT status FROM open_orders WHERE order_id='ord-1'").fetchone()
    assert row == ("filling",)
