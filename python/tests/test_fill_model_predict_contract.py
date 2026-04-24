"""Wave-0 scaffold for FILL-05 (predict contract).

All tests in this file are marked ``wave-0-scaffold`` and skipped until Plan 02-03
implements ``boros_brain.fill_model.predictor``.

Test IDs: T-02-P-01 through T-02-P-04.
"""

from __future__ import annotations

import pytest

# Import guarded inside each test to prevent collection failure when the module
# does not yet exist (plan 02-03 creates it).


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-03")
def test_predict_in_unit_interval() -> None:
    """T-02-P-01: predict() returns p in [0.0, 1.0] on happy-path inputs.

    Constructs a fitted artifact from the synthetic Poisson fixture,
    calls predict() with valid current_features, asserts 0.0 <= out.p_fill_this_epoch <= 1.0.
    """
    from boros_brain.fill_model.predictor import predict  # noqa: F401

    raise NotImplementedError("implemented in plan 02-03")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-03")
def test_predict_raises_on_nan() -> None:
    """T-02-P-02: predict() raises FillModelStaleFeatureError when a covariate is NaN.

    One NaN in current_features triggers FillModelStaleFeatureError with the
    missing_features field populated. No silent fallback to exp(β₀) baseline.
    """
    from boros_brain.fill_model.predictor import FillModelStaleFeatureError, predict  # noqa: F401

    raise NotImplementedError("implemented in plan 02-03")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-03")
def test_predict_monotone_in_depth() -> None:
    """T-02-P-03: predict() is monotone-non-increasing in depth (delta) ceteris paribus.

    Uses Hypothesis property test: increasing the order's distance from mid price
    (delta) should non-increase the fill probability (deeper = harder to fill).
    """
    from boros_brain.fill_model.predictor import predict  # noqa: F401

    raise NotImplementedError("implemented in plan 02-03")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-03")
def test_predict_monotone_in_queue() -> None:
    """T-02-P-04: predict() is monotone-non-increasing in queue_ahead ceteris paribus.

    Uses Hypothesis property test: a larger queue of orders ahead of ours at
    depth delta should non-increase our fill probability.
    """
    from boros_brain.fill_model.predictor import predict  # noqa: F401

    raise NotImplementedError("implemented in plan 02-03")
