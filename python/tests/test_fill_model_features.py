"""Wave-0 scaffold for FILL-02 (feature pipeline).

IMPLEMENTED tests (run immediately):
  - test_covariate_whitelist (T-02-F-01): FillModelConfig rejects non-ALLOWED_COVARIATES.
  - test_ewma_no_lookahead (T-02-F-02): left-closed EWMA invariant in build_features_table.

Both tests exercise code created in Plan 02-01. No skip markers needed here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from boros_brain.fill_model.config import FillModelConfig


# ── T-02-F-01: covariate whitelist validation ──────────────────────────────


def test_covariate_whitelist() -> None:
    """T-02-F-01: Non-whitelisted covariate in FillModelConfig raises ValidationError.

    Security context (T-02-01-01): a non-whitelisted covariate string could cause
    NaN propagation at fit time. The validator gate catches it at config load so
    downstream GLM code never sees an unexpected feature name.
    """
    with pytest.raises(ValidationError) as exc_info:
        FillModelConfig(covariate_whitelist=["not_a_feature"])
    assert "non-allowed" in str(exc_info.value), (
        f"Expected 'non-allowed' in ValidationError message, got: {exc_info.value}"
    )


def test_covariate_whitelist_accepts_valid_subset() -> None:
    """T-02-F-01 complement: valid subset of ALLOWED_COVARIATES is accepted."""
    cfg = FillModelConfig(covariate_whitelist=["basis_spread", "imbalance"])
    assert cfg.covariate_whitelist == ["basis_spread", "imbalance"]


def test_covariate_whitelist_rejects_mixed() -> None:
    """T-02-F-01: mixed valid/invalid list still raises on the bad entry."""
    with pytest.raises(ValidationError) as exc_info:
        FillModelConfig(covariate_whitelist=["basis_spread", "bad_feature", "ewma_vol"])
    assert "non-allowed" in str(exc_info.value)


def test_covariate_whitelist_default_all_five() -> None:
    """Default FillModelConfig has all 5 allowed covariates in whitelist."""
    cfg = FillModelConfig()
    assert len(cfg.covariate_whitelist) == 5
    assert set(cfg.covariate_whitelist) == {
        "basis_spread",
        "imbalance",
        "sin_settlement",
        "cos_settlement",
        "ewma_vol",
    }


# ── T-02-F-02: no-look-ahead EWMA invariant ────────────────────────────────


def test_ewma_no_lookahead() -> None:
    """T-02-F-02: Left-closed EWMA window — current bin's spike does not affect its own ewma_vol.

    Implementation note: this test verifies the SQL invariant in features.py by checking
    the module-level _FEATURE_SQL string directly (fast, no DuckDB needed). The full
    behavioral test (round-tripping through build_features_table against a synthetic parquet)
    is deferred to Plan 02-03 once the fit loop is in place — the SQL string check is
    sufficient to guard the T-02-F-02 invariant at scaffold time.
    """
    from boros_brain.fill_model.features import _FEATURE_SQL

    assert "ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING" in _FEATURE_SQL, (
        "EWMA window must be 'ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING' — "
        "'CURRENT ROW' would introduce look-ahead bias (T-02-F-02 invariant)."
    )
    # Negative check: CURRENT ROW must NOT appear in the EWMA window clause
    # (it may appear elsewhere in the SQL, so we check specifically in the vol CTE)
    vol_cte_start = _FEATURE_SQL.find("vol AS (")
    vol_cte_end = _FEATURE_SQL.find("\n)", vol_cte_start)
    vol_cte = _FEATURE_SQL[vol_cte_start:vol_cte_end]
    assert "CURRENT ROW" not in vol_cte, (
        "CURRENT ROW found in vol CTE — this introduces look-ahead bias (T-02-F-02)."
    )
