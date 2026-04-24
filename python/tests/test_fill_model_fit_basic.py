"""Wave-0 scaffold for FILL-01 (Poisson GLM fit).

Tests that depend on Plan 02-03's fit/predict code are marked ``wave-0-scaffold`` and
skipped until that plan implements ``boros_brain.fill_model.fitter``.

Test IDs: T-02-M-01 through T-02-M-02.

Note on test_covariate_whitelist: T-02-F-01 is implemented in
test_fill_model_features.py::test_covariate_whitelist — not duplicated here.
"""

from __future__ import annotations

import pytest

# Import guarded inside each test to prevent collection failure when the module
# does not yet exist (plan 02-03 creates it).


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-03")
def test_fit_converges_on_synthetic_poisson() -> None:
    """T-02-M-01: statsmodels Poisson GLM converges on fill_model_synthetic_poisson.parquet.

    Load the 2000-bin fixture (known β_true = [-1.0, 0.5, -0.3, 0.1, 0.1, 0.2]).
    Run fit_market_side(). Assert:
      - artifact.converged is True
      - |β_hat[i] - β_true[i]| < 3 × bse[i] for each parameter i
    """
    from boros_brain.fill_model.fitter import fit_market_side  # noqa: F401

    raise NotImplementedError("implemented in plan 02-03")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-03")
def test_fit_degrades_on_sparse() -> None:
    """T-02-M-02: fit on a 10-row DataFrame marks fit_status='degraded' without exception.

    A Poisson GLM on 10 rows with 6 parameters violates the
    min_events_per_param_ratio=10 guard. The fitter must return gracefully with
    artifact.fit_status == 'degraded' rather than raising.
    """
    from boros_brain.fill_model.fitter import fit_market_side  # noqa: F401

    raise NotImplementedError("implemented in plan 02-03")


def test_covariate_whitelist_covered_in_features_test() -> None:
    """T-02-F-01 note: covariate whitelist validation is covered in
    test_fill_model_features.py::test_covariate_whitelist.
    This stub documents that the coverage is intentionally in the features test,
    not here, to avoid duplication.
    """
    # See test_fill_model_features.py::test_covariate_whitelist for T-02-F-01.
    pass
