"""FillModelConfig — Pydantic sub-model for all NHPP fill model knobs (FILL-01..06).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
This mirrors the pattern in brain.manifest.schema (lines 20-23).

[[fill-model-library-decision-tick-vs-statsmodels]]: statsmodels on critical path.
[[covariate-selection-v05]]: 5 model features (4 raw covariates) selected for v0.5.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import ALLOWED_COVARIATES, DEFAULT_COVARIATE_WHITELIST


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class FillModelConfig(StrictBase):
    """Knobs for the NHPP fill model (FILL-01..06). Reflection-surfaced in RUN_MANIFEST.

    All 11 knobs here are the single source of truth (PROTO-04). Adding a knob in
    fill_model code without adding it here is a bug — the manifest round-trip test
    (test_manifest_contains_all_knobs.py::test_fill_model_leaves_surfaced) will catch it.
    """

    window_days: int = Field(14, ge=7, le=30)
    """Number of days of trade history used to build the feature table for each fit."""

    bin_duration_s: float = Field(60.0, ge=30.0, le=300.0)
    """Width of each time bin in seconds. Trade counts per bin are the Poisson response."""

    refit_cadence_s: float = Field(900.0, ge=60.0, le=3600.0)
    """How often (seconds) the refit loop re-runs fit_market_side and updates the cached artifact."""

    covariate_whitelist: list[str] = Field(
        default_factory=lambda: list(DEFAULT_COVARIATE_WHITELIST)
    )
    """Subset of ALLOWED_COVARIATES to include in the GLM design matrix for this run."""

    queue_tracker_bias_mode: Literal["pessimistic", "optimistic", "realized"] = "pessimistic"
    """Which queue-ahead estimate to use for the P(fill) calculation.
    pessimistic = worst-case (max queue depth ahead of our order).
    """

    gof_ks_pval_threshold: float = Field(0.0, ge=0.0, le=0.5)
    """KS-test p-value below which a fit triggers a GoF degradation warning.
    0.0 = no warning on KS (use gof_lr_ratio_threshold alone).
    """

    gof_lr_ratio_threshold: float | None = None
    """Likelihood-ratio GoF threshold; bootstrap-calibrated at first fit (Plan 02-04).
    None until the calibration run populates it.
    """

    fit_warn_staleness_s: float = Field(1800.0, ge=600.0, le=7200.0)
    """Emit fill_model.fit_stale warning if last successful fit is older than this."""

    fit_max_staleness_s: float = Field(3600.0, ge=0.0, le=28800.0)
    """Treat model as failed-open if last successful fit is older than this."""

    bracket_width_warn_multiplier: float = Field(0.5, ge=0.1, le=2.0)
    """Warn if bracket width (pessimistic - optimistic) exceeds
    bracket_width_warn_multiplier × median historical bracket width.
    """

    min_events_per_param_ratio: int = Field(10, ge=5, le=50)
    """Minimum ratio of events to GLM parameters. Below this, fit_status='degraded'."""

    @field_validator("covariate_whitelist")
    @classmethod
    def _whitelist_subset(cls, v: list[str]) -> list[str]:
        """Reject any covariate name not in ALLOWED_COVARIATES (T-02-F-01)."""
        bad = [x for x in v if x not in ALLOWED_COVARIATES]
        if bad:
            raise ValueError(
                f"covariate_whitelist contains non-allowed entries: {bad}. "
                f"Allowed: {sorted(ALLOWED_COVARIATES)}"
            )
        return v
