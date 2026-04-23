"""Wave-0 tracer-bullet scaffolding.

These stubs exist so pytest collection proves the test module is wired up.
Real assertions land in plan 01-02 (SQLite) and 01-03 (ZMQ, manifest writer).
"""

from __future__ import annotations

import pytest


@pytest.mark.wave0_scaffold
@pytest.mark.skip(reason="RUN_MANIFEST writer wired by plan 01-03 (INFRA-06)")
def test_manifest_writer_emits_first_line() -> None:
    pass


@pytest.mark.wave0_scaffold
@pytest.mark.skip(reason="ZMQ bus wired by plan 01-03 (INFRA-05)")
def test_zmq_echo_roundtrip_under_10ms() -> None:
    pass


@pytest.mark.wave0_scaffold
@pytest.mark.skip(reason="SQLite open_orders writer wired by plan 01-02 (INFRA-03)")
def test_sqlite_open_orders_roundtrip() -> None:
    pass
