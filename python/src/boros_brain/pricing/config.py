"""PricingConfig — Pydantic sub-model for PENDLE/USD pricing (PROTO-04 SSoT).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
v0.5 = operator-manual price; v1.0 candidates Chainlink / Pyth once wired.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class PricingConfig(StrictBase):
    """PENDLE/USD pricing — operator-manual in v0.5; oracle-fed in v1.0.

    Knob inventory (PROTO-04 SSoT):
      pendle_price_usd, price_source, price_staleness_warn_s, price_staleness_halt_s.
    """

    pendle_price_usd: float = Field(7.0, ge=0.1, le=1000.0)
    """Operator-supplied PENDLE/USD price. v1.0 will replace with oracle read."""

    price_source: Literal["manual", "chainlink", "pyth"] = "manual"
    """Source enum. v0.5 fixed at 'manual'; v1.0 may flip to a live oracle."""

    price_staleness_warn_s: float = Field(86400.0, ge=3600.0, le=604800.0)
    """Emit pricing.price_stale warning when last update older than this (default 1 day)."""

    price_staleness_halt_s: float = Field(604800.0, ge=86400.0, le=2_592_000.0)
    """Halt when last update older than this (default 7 days)."""
