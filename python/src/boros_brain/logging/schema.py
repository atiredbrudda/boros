"""Shared log-record schema (INFRA-07).

Python structlog and TypeScript pino both emit records with AT LEAST these fields.
Event-specific extra keys are allowed (`model_config extra='allow'`) so individual
events can attach structured payloads.

Keeping the field set small and authoritative means `jq 'select(.run_id=="…")'`
across both tiers' log files returns a coherent cross-process stream.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

#: Minimum set of field names every log record must carry on both tiers.
MIN_FIELDS = frozenset({"ts", "level", "event", "run_id", "tier", "logger", "pid"})


class LogRecord(BaseModel):
    """Minimum shared record shape. `extra='allow'` — event payload keys are free."""

    model_config = ConfigDict(extra="allow")

    ts: str
    level: str
    event: str
    run_id: str
    tier: str
    logger: str
    pid: int
