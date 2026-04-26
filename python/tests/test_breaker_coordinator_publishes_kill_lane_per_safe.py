"""SAFE composition RED stub — coordinator publishes correct kill-lane message per breaker.

Parametrized over the 10 trip cases SAFE-01..09 + B5 (loss_fit_degraded).
Each parameter is the breaker name + the trigger scenario that the corresponding
plan 04-04/05 unit-test builds.

This file is RED-skipped via pytest.importorskip at module top until plan 04-06
lands the BreakerCoordinator. The tests will be turned GREEN in Plan 04-06 Task 6
(real per-SAFE breaker instantiation, real CmdBus, ipc_dir fixture, assert correct
ZMQ message kind on the priority KILL lane).

See test_breaker_coordinator_exclusive.py for the coordinator exclusivity tests
that also land in 04-06 (SAFE-10).

Wave 0 invariant: this file MUST collect (not error) with importorskip-driven SKIP status.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: BreakerCoordinator lands in Plan 04-06.
# All tests in this file skip until the coordinator module exists.
coordinator_mod = pytest.importorskip("boros_brain.decision.breaker_coordinator")
BreakerCoordinator = coordinator_mod.BreakerCoordinator
breakers_base = pytest.importorskip("boros_brain.decision.breakers.base")
BreakerSignal = breakers_base.BreakerSignal

from boros_brain.bus.cmd import CmdBus  # noqa: E402

# ---------------------------------------------------------------------------
# Parametrize over every SAFE scenario. Each tuple:
#   (breaker_name, kill_command_kind, scenario_description)
# The actual breaker fixture that generates the trip scenario is wired in Plan
# 04-06 Task 6 once all breaker implementations exist. The stub below verifies
# the coordinator correctly plumbs each breaker's kill_command_kind into the
# ZMQ KILL-lane message.
# ---------------------------------------------------------------------------
_SAFE_SCENARIOS = [
    # SAFE-01 — margin trajectory breach
    ("margin_trajectory", "HALVE_POSITION_AND_ALERT", "SAFE-01 margin breach"),
    # SAFE-02 — oracle staleness
    ("oracle_stale", "PAUSE_AND_ALERT", "SAFE-02 fIndex stale"),
    # SAFE-03 — CLO removal (either threshold = 0)
    ("clo_removal", "CANCEL_ALL_AND_RECALIBRATE", "SAFE-03 CLO removed"),
    # SAFE-04 — CLO shift (>5 ticks)
    ("clo_shift", "CANCEL_ALL_AND_RECALIBRATE", "SAFE-04 CLO shift"),
    # SAFE-05 — fill rate runaway (K=4 fills/hour)
    ("fill_rate", "PAUSE_AND_ALERT", "SAFE-05 fill runaway"),
    # SAFE-06 — competition collapse (>50% drop)
    ("competition", "HALVE_POSITION_AND_ALERT", "SAFE-06 competition drop"),
    # SAFE-07 — maturity migration
    ("maturity", "ROLL_POSITION", "SAFE-07 near maturity"),
    # SAFE-08 — side budget drift (>=30%)
    ("side_budget", "HALVE_POSITION_AND_ALERT", "SAFE-08 side drift"),
    # SAFE-09 — underlying APR stale (>2× cadence)
    ("underlying_stale", "PAUSE_AND_ALERT", "SAFE-09 underlying stale"),
    # B5 absorbed — loss fit degraded
    ("loss_fit_degraded", "SHRINK_TO_Q_MIN", "B5 loss grid degraded"),
]


@pytest.mark.parametrize(
    "breaker_name, expected_kill_kind, scenario",
    _SAFE_SCENARIOS,
    ids=[s[0] for s in _SAFE_SCENARIOS],
)
@pytest.mark.asyncio
async def test_coordinator_publishes_kill_lane_per_safe(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    ipc_dir: Path,
    breaker_name: str,
    expected_kill_kind: str,
    scenario: str,
) -> None:
    """SAFE-01..09 + B5 composition: coordinator sends correct kill_command_kind on KILL lane.

    For each breaker scenario, a stubbed breaker returns a tripped BreakerSignal with
    the expected kill_command_kind. The coordinator must:
    1. Receive the tripped signal from the breaker.
    2. Publish a kill-lane ZMQ message with kind="kill" and the correct kill_command_kind.
    3. NOT publish any cmd-lane (PLACE/CANCEL) messages.

    This test turns GREEN in Plan 04-06 Task 6 when the real breaker instances
    and the full coordinator.tick() loop are wired together.
    """
    import zmq
    import zmq.asyncio

    cmd_endpoint = f"ipc://{ipc_dir}/{breaker_name}_cmd"
    kill_endpoint = f"ipc://{ipc_dir}/{breaker_name}_kill"

    ctx = zmq.asyncio.Context.instance()
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.bind(kill_endpoint)

    import asyncio

    await asyncio.sleep(0.05)

    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)

    # Build a stub breaker that returns the expected tripped signal.
    class _StubBreaker:
        name = breaker_name

        async def check(self, **kw) -> BreakerSignal:
            return BreakerSignal(
                tripped=True,
                reason=f"{breaker_name}_triggered",
                kill_command_kind=expected_kill_kind,
            )

    coord = BreakerCoordinator(
        cmd_bus=bus,
        config=default_config,
        run_id=f"test-{breaker_name}",
        gas_cache=None,
        breakers=[_StubBreaker()],
    )

    await coord.tick(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        current_chain_ts=1_700_000_000,
    )

    kill_msg = await asyncio.wait_for(kill_pull.recv_json(), timeout=1.0)
    assert kill_msg.get("kind") == "kill", f"{scenario}: expected kind='kill', got {kill_msg!r}"
    assert kill_msg.get("kill_command_kind") == expected_kill_kind, (
        f"{scenario}: expected kill_command_kind={expected_kill_kind!r}, " f"got {kill_msg.get('kill_command_kind')!r}"
    )

    kill_pull.close()
    bus.close()
