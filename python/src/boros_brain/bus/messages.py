"""ZMQ message schemas — Python Pydantic side (INFRA-05, T-03-03, T-03-04).

The TS side in `ts/src/boros_hands/bus/messages.ts` hand-mirrors these as Zod
schemas. Cross-language drift is caught by `test_zmq_schema_mirror` (see
`ts/tests/bus/zmq_echo.test.ts`) which round-trips a Pydantic `model_dump(mode='json')`
through `z.parse(...)` and asserts equality.

`extra='forbid'` on every message means an unknown field from the peer is a
loud `ValidationError` — defense against T-03-04 (unvalidated input).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictMsg(BaseModel):
    """Base: strict field set, no extras. Used for all cmd/event payloads."""

    model_config = ConfigDict(extra="forbid")


class PlaceCmd(StrictMsg):
    kind: Literal["place"] = "place"
    order_id: str
    market_id: str
    side: Literal["long", "short"]
    depth_ticks: int
    size_wei: str
    rate: int
    run_id: str


class CancelCmd(StrictMsg):
    kind: Literal["cancel"] = "cancel"
    order_id: str
    run_id: str


class KillCmd(StrictMsg):
    kind: Literal["kill"] = "kill"
    reason: str
    run_id: str
    kill_command_kind: str | None = None  # SAFE-10: breaker-specific action kind for operator triage


class Heartbeat(StrictMsg):
    kind: Literal["heartbeat"] = "heartbeat"
    from_tier: Literal["brain", "hands"]
    ts_ms: int
    run_id: str


class LostSibling(StrictMsg):
    kind: Literal["lost_sibling"] = "lost_sibling"
    observer: Literal["brain", "hands"]
    missing_since_ts_ms: int
    run_id: str


class RunManifestAnnounce(StrictMsg):
    kind: Literal["run_manifest_announce"] = "run_manifest_announce"
    run_id: str
    started_at: str
    parent_run_id: str | None = None
