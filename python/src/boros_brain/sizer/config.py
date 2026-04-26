"""SizerConfig — Pydantic sub-model for REWARD-03 sizing-optimizer knobs.

Re-declares a local StrictBase to avoid circular imports with brain.config.schema
(matches the pattern in brain.fill_model.config / brain.loss_model.config /
brain.reward_model.config / brain.pricing.config).

Knob inventory (PROTO-04 SSoT):
  - 6 SizerConfig knobs: collateral_usd, q_min_pendle, q_max_safety_margin,
    optimizer_grid_points, optimizer_method, notional_per_yu_usd.

[[sizing-optimizer-sub-cap-regime-v05]]
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class SizerConfig(StrictBase):
    """Knobs for the sizing optimizer (REWARD-03/04). Reflection-surfaced in
    RUN_MANIFEST automatically; PROTO-04 SSoT.

    All 6 knobs here are the single source of truth. Adding a knob in sizer
    code without adding it here is a bug — manifest reflection round-trip
    catches it.
    """

    collateral_usd: float = Field(100.0, ge=10.0, le=1_000_000.0)
    """Operator-committed collateral in USD. v0.5 anchor: $100."""

    q_min_pendle: float = Field(1e-3, ge=1e-18, le=1.0)
    """Hard floor on our order size in PENDLE. Derived from fee-amortization floor."""

    q_max_safety_margin: float = Field(0.9, ge=0.1, le=1.0)
    """Fraction of collateral-derived Q_max we actually use (safety buffer)."""

    optimizer_grid_points: int = Field(50, ge=10, le=500)
    """Grid density for the 1-D optimization over [Q_min, upper]."""

    optimizer_method: Literal["grid_only", "grid_plus_scipy", "scipy_only"] = "grid_plus_scipy"
    """Dispatch enum:
      grid_only       — deterministic-bit-for-bit grid argmax.
      grid_plus_scipy — grid argmax + scipy.optimize.minimize_scalar polish (default).
      scipy_only      — skip grid; bounded scipy minimize_scalar over [q_min, upper].
    """

    notional_per_yu_usd: float = Field(1.0, ge=0.01, le=10_000_000.0)
    """Per-market USD notional per 1 PENDLE-equivalent YU. Operator-calibrated per market.

    At $100 collateral with notional_per_yu_usd=90000 (ETHUSDT-29MAY2026 placeholder),
    Q_max = collateral_usd × q_max_safety_margin / notional_per_yu_usd
          = 100 × 0.9 / 90000 ≈ 1e-3 PENDLE,
    which equals q_min_pendle — the collateral-constrained sub-cap regime fixed point
    that satisfies Phase 3 ROADMAP Success Criterion #3.

    Upper bound 1e7 USD/PENDLE-YU is generous; operator-calibrated values for
    real markets sit in 1e4..1e6 range. Lower bound 0.01 USD/PENDLE-YU keeps
    the no-conversion test path (notional_per_yu_usd=1.0) valid for unit tests.
    """
