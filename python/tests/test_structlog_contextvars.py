"""INFRA-07 — structlog `run_id` propagates through contextvars.

PITFALLS §D2 critical requirement: `asyncio.create_task` + `asyncio.gather` must
inherit the active `run_id` automatically. Python 3.7+ contextvars guarantee this
as long as `structlog.contextvars.bind_contextvars` is used at configuration time.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from boros_brain.logging.structlog_setup import configure_logging, get_logger


def _find_log_file(logs_dir: Path, run_id: str, tier: str) -> Path:
    candidates = list(logs_dir.rglob(f"{run_id}.{tier}.log.jsonl"))
    assert candidates, f"no log file for run_id={run_id} under {logs_dir}"
    return candidates[0]


def test_structlog_records_carry_run_id(tmp_path: Path) -> None:
    configure_logging(run_id="TEST_RUN_SIMPLE", tier="brain", logs_dir=tmp_path, first_manifest_line=None)
    get_logger("boros_brain.test").info("plain_event", k=1)

    path = _find_log_file(tmp_path, "TEST_RUN_SIMPLE", "brain")
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert lines, "expected at least one log record"
    assert all(r["run_id"] == "TEST_RUN_SIMPLE" for r in lines)
    assert all(r["tier"] == "brain" for r in lines)


def test_structlog_contextvars_survive_create_task(tmp_path: Path) -> None:
    configure_logging(run_id="TEST_CREATE_TASK", tier="brain", logs_dir=tmp_path, first_manifest_line=None)

    async def inner() -> None:
        get_logger("boros_brain.child").info("inner_event")

    async def outer() -> None:
        task = asyncio.create_task(inner())
        await task

    asyncio.run(outer())

    path = _find_log_file(tmp_path, "TEST_CREATE_TASK", "brain")
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    inner_records = [r for r in records if r.get("event") == "inner_event"]
    assert inner_records, "inner event missing from log"
    assert all(r["run_id"] == "TEST_CREATE_TASK" for r in inner_records)


def test_structlog_contextvars_survive_gather(tmp_path: Path) -> None:
    configure_logging(run_id="TEST_GATHER", tier="brain", logs_dir=tmp_path, first_manifest_line=None)

    async def inner(tag: str) -> None:
        get_logger("boros_brain.child").info("gather_event", tag=tag)

    async def outer() -> None:
        await asyncio.gather(inner("a"), inner("b"))

    asyncio.run(outer())

    path = _find_log_file(tmp_path, "TEST_GATHER", "brain")
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    gather_records = [r for r in records if r.get("event") == "gather_event"]
    assert len(gather_records) == 2
    assert {r["tag"] for r in gather_records} == {"a", "b"}
    assert all(r["run_id"] == "TEST_GATHER" for r in gather_records)
