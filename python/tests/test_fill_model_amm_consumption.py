"""Wave-0 scaffold for FILL-04 (AMM consumption tracker).

All tests in this file are marked ``wave-0-scaffold`` and skipped until Plan 02-02
implements ``boros_brain.fill_model.amm_consumption``.

Test IDs: T-02-A-01 through T-02-A-02.
"""

from __future__ import annotations

import pytest

# Import guarded inside each test to prevent collection failure when the module
# does not yet exist (plan 02-02 creates it).


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-02")
def test_amm_share_non_negative() -> None:
    """T-02-A-01: compute_amm_share_timeseries returns >= 0.0 for all (delta, t) on fixture.

    Uses Hypothesis property test: for arbitrary positive delta and t values,
    the AMM share estimate must be non-negative (share can be zero but not negative).
    """
    from boros_brain.fill_model.amm_consumption import compute_amm_share_timeseries  # noqa: F401

    raise NotImplementedError("implemented in plan 02-02")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-02")
def test_epoch_conservation() -> None:
    """T-02-A-02: per-epoch runtime conservation identity.

    assert_epoch_conservation() succeeds on a balanced-flow synthetic epoch,
    raises AMMConsumptionIdentityError on an unbalanced epoch fixture.
    This mirrors the AMM conservation test pattern from test_amm_conservation.py.
    """
    from boros_brain.fill_model.amm_consumption import (  # noqa: F401
        AMMConsumptionIdentityError,
        assert_epoch_conservation,
    )

    raise NotImplementedError("implemented in plan 02-02")
