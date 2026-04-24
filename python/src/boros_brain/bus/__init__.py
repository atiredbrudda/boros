"""ZMQ bus (INFRA-05) — cmd/kill PUSH/PULL + events PUB/SUB + heartbeat.

Public API:
  - messages:          Pydantic StrictMsg types (PlaceCmd, CancelCmd, KillCmd, ...)
  - CmdBus:            brain-side PUSH sockets (cmd + kill lanes)
  - EventBus:          bidirectional PUB/SUB bus (two-endpoint topology)
  - HeartbeatMonitor:  5s heartbeat + 3-miss lost-sibling protocol
  - LOST_SIBLING_EVENT: literal event name for grepping logs
"""

from .cmd import CmdBus
from .events import EventBus
from .heartbeat import LOST_SIBLING_EVENT, HeartbeatMonitor
from .messages import (
    CancelCmd,
    Heartbeat,
    KillCmd,
    LostSibling,
    PlaceCmd,
    RunManifestAnnounce,
    StrictMsg,
)

__all__ = [
    "CancelCmd",
    "CmdBus",
    "EventBus",
    "Heartbeat",
    "HeartbeatMonitor",
    "KillCmd",
    "LOST_SIBLING_EVENT",
    "LostSibling",
    "PlaceCmd",
    "RunManifestAnnounce",
    "StrictMsg",
]
