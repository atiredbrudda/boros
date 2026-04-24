"""RUN_MANIFEST Pydantic model (INFRA-06, PROTO-01).

The manifest is a strict contract. `extra='forbid'` + `frozen=True` means:
  - A writer that tries to attach an undocumented field raises ValidationError.
  - Once built, a manifest is immutable — downstream analyzers can cache it freely.

Fields `chain_time_drift_at_start_seconds` and `agent_wallet_gas_balance_at_start`
are reserved here so the manifest shape is stable across phases; they are None in
Phase 1 and populated by INFRA-14 (chain-time drift) and Phase 6 (agent wallet gas)
respectively.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RunManifest(StrictBase):
    run_id: str
    parent_run_id: str | None = None
    started_at: str
    mode: str
    strategy_version: str
    git_sha: str
    git_dirty: bool
    market_id: str
    side: str
    wallet_address_hash: str
    config: dict[str, Any]
    chain_time_drift_at_start_seconds: float | None = None
    agent_wallet_gas_balance_at_start: float | None = None
