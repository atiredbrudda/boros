"""main.py wiring — decision loop spawn + coordinator halt-callback tests (RED until 04-06).

Covers:
  - test_decision_loop_task_created: asyncio task named '_decision_loop' (or similar)
    exists in asyncio.all_tasks() after run() boot
  - test_chain_cache_halt_callback_wired: chain_cache.halt_callback is coord.halt_via_chain_time
    after boot (xfail until 04-06)

These tests validate that Plan 04-06 correctly wires the decision loop into the
existing main.py boot sequence without breaking the Phase 1-3 boot flow.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# RED state guard: BreakerCoordinator lands in Plan 04-06.
# The test collects but skips until the coordinator exists.
breaker_coordinator_mod = pytest.importorskip("boros_brain.decision.breaker_coordinator")

from boros_brain.config.schema import BotConfig  # noqa: E402

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_decision_loop_task_created(
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    ipc_dir: Path,
    monkeypatch,
) -> None:
    """After run() boot, an asyncio task for the decision loop must exist.

    Stubs out the heavy boot steps (manifest write, ZMQ, refit) so the test
    can assert purely on task-spawn behavior.
    """
    from boros_brain import main as brain_main

    # Stub out expensive boot steps so the test terminates quickly.
    monkeypatch.setattr("boros_brain.main._run_initial_fill_fit", AsyncMock())
    monkeypatch.setattr("boros_brain.main._run_initial_loss_fit", AsyncMock())
    monkeypatch.setattr("boros_brain.main._write_manifest", AsyncMock())

    tasks_snapshot: list[asyncio.Task] = []

    async def _capture_tasks():
        """Let the loop start, snapshot tasks, then cancel everything."""
        await asyncio.sleep(0.1)
        tasks_snapshot.extend(asyncio.all_tasks())

    # Run the brain with a tight timeout — collect the task names.
    try:
        await asyncio.wait_for(
            asyncio.gather(
                brain_main.run(
                    config=default_config,
                    sqlite_path=tmp_sqlite_path,
                    mode="paper",
                ),
                _capture_tasks(),
                return_exceptions=True,
            ),
            timeout=1.0,
        )
    except (asyncio.TimeoutError, Exception):
        pass  # Expected — we cancel boot early

    task_names = [t.get_name() for t in tasks_snapshot]
    decision_tasks = [n for n in task_names if "decision" in n.lower() or "loop" in n.lower()]
    assert decision_tasks, (
        f"No decision loop task found in asyncio.all_tasks(). "
        f"Task names were: {task_names}. "
        "Plan 04-06 must spawn a '_decision_loop' task during boot."
    )


@pytest.mark.xfail(reason="BreakerCoordinator.halt_via_chain_time wiring lands in 04-06")
@pytest.mark.asyncio
async def test_chain_cache_halt_callback_wired(
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    monkeypatch,
) -> None:
    """After boot, chain_cache.halt_callback must be coord.halt_via_chain_time.

    Plan 04-06 replaces the default _default_halt_callback with the coordinator's
    halt_via_chain_time method so chain-time drift triggers an orderly circuit-breaker
    shutdown rather than an abrupt process kill.
    """
    from boros_brain import main as brain_main

    captured = {}

    original_run = brain_main.run

    async def _spy_run(**kw):
        await original_run(**kw)
        # After boot, chain_cache.halt_callback should be the coordinator's method.
        captured["halt_callback"] = getattr(
            brain_main._chain_cache, "halt_callback", None
        )

    monkeypatch.setattr("boros_brain.main.run", _spy_run)

    try:
        await asyncio.wait_for(
            brain_main.run(config=default_config, sqlite_path=tmp_sqlite_path, mode="paper"),
            timeout=0.5,
        )
    except (asyncio.TimeoutError, Exception):
        pass

    cb = captured.get("halt_callback")
    assert cb is not None, "halt_callback not set on chain_cache after boot"
    assert "halt_via_chain_time" in getattr(cb, "__name__", ""), (
        f"halt_callback should be coord.halt_via_chain_time, got {cb!r}"
    )
