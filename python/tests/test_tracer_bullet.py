"""Wave-0 tracer-bullet scaffolding.

One of the three stubs flips from skip → green as each dependent plan lands:
  - test_sqlite_open_orders_roundtrip  → wired by plan 01-02 (INFRA-03)  ✓
  - test_manifest_writer_emits_first_line → wired by plan 01-03 (INFRA-06)
  - test_zmq_echo_roundtrip_under_10ms  → wired by plan 01-03 (INFRA-05)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from boros_brain.state import writers
from boros_brain.state.db import open_connection

_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


@pytest.mark.wave0_scaffold
@pytest.mark.skip(reason="RUN_MANIFEST writer wired by plan 01-03 (INFRA-06)")
def test_manifest_writer_emits_first_line() -> None:
    pass


@pytest.mark.wave0_scaffold
@pytest.mark.skip(reason="ZMQ bus wired by plan 01-03 (INFRA-05)")
def test_zmq_echo_roundtrip_under_10ms() -> None:
    pass


@pytest.mark.wave0_scaffold
def test_sqlite_open_orders_roundtrip(tmp_path: Path) -> None:
    """INFRA-03 un-skip: alembic → seed via TEST_ONLY writer → raw SELECT reads row back.

    Wired by plan 01-02. The TEST_ONLY-guarded Python writer for `open_orders`
    exists exactly for this kind of integration seeding; the production hands-side
    writer lives in ts/src/boros_hands/state/sqlite_writer.ts.
    """
    db = tmp_path / "tracer.sqlite"
    with open_connection(db):
        pass
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")

    with open_connection(db) as conn:
        writers.open_orders.insert_open_order(
            conn,
            order_id="ord-tracer",
            market_id="ETHUSDT-29MAY2026",
            side="long",
            depth_ticks=50,
            size_wei="1000000000000000000",
            rate=9400,
            status="filling",
            placed_at_ts=1_714_000_000,
            run_id="run-tracer",
        )
        row = conn.execute(
            "SELECT order_id, status, market_id, side FROM open_orders WHERE order_id='ord-tracer'"
        ).fetchone()

    assert row == ("ord-tracer", "filling", "ETHUSDT-29MAY2026", "long")
