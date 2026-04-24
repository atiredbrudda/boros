"""Wave-0 scaffold for FILL-06 (calibration + GoF).

All tests in this file are marked ``wave-0-scaffold`` and skipped until Plan 02-04
implements ``boros_brain.fill_model.calibration`` and ``run_fill_model_refit_loop``.

Test IDs: T-02-C-01 through T-02-C-03.
"""

from __future__ import annotations

import pytest

# Import guarded inside each test to prevent collection failure when the module
# does not yet exist (plan 02-04 creates it).


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-04")
def test_calibration_on_holdout() -> None:
    """T-02-C-01: calibration predicted P(fill) matches realized within ±5pp per decile.

    Integration test:
    1. Fit on 80% of fill_model_synthetic_poisson.parquet.
    2. Calibrate on 20% hold-out.
    3. Assert |predicted_decile_mean - realized_decile_rate| < 0.05 for each decile.
    """
    from boros_brain.fill_model.calibration import calibrate_model  # noqa: F401

    raise NotImplementedError("implemented in plan 02-04")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-04")
def test_refit_loop_writes_artifact() -> None:
    """T-02-C-02: rolling 14-day refit loop writes a new fit artifact each cadence.

    Spawns run_fill_model_refit_loop in a pytest-asyncio context.
    Advances the clock by refit_cadence_s. Asserts a new row appears in the
    fill_model_fits SQLite table with an updated fit timestamp.
    """
    from boros_brain.fill_model.refit_loop import run_fill_model_refit_loop  # noqa: F401

    raise NotImplementedError("implemented in plan 02-04")


@pytest.mark.skip(reason="wave-0-scaffold: implemented in plan 02-04")
def test_degraded_warning_on_regime_shift() -> None:
    """T-02-C-03: GoF below bootstrap threshold triggers fill_model.fit_degraded log event.

    Loads fill_model_regime_shift.parquet.
    Fits on pre-regime bins (0..1399), evaluates GoF on post-regime bins (1400..1999).
    Asserts structlog.testing.capture_logs() includes an event with
    event='fill_model.fit_degraded'.
    """
    from boros_brain.fill_model.calibration import evaluate_gof  # noqa: F401

    raise NotImplementedError("implemented in plan 02-04")
