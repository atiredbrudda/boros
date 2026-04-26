"""BACK-07 — block bootstrap determinism (same manifest → same distribution).

Test functions:
  - test_same_manifest_yields_same_p5: two runs with same manifest → identical p5 bootstrap
  - test_seed_from_manifest_is_deterministic: same manifest → same uint64 seed
  - test_explicit_rng_no_global_state_contamination: bootstrap twice same session → identical (Pitfall #6 guard)

Turns GREEN in Plan 05-07 when boros_brain.backtest.bootstrap lands.

[[backtest-bootstrap-methodology-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-07.
bootstrap_mod = pytest.importorskip("boros_brain.backtest.bootstrap")
seed_from_manifest = bootstrap_mod.seed_from_manifest
make_rng = bootstrap_mod.make_rng
block_bootstrap_pnl = bootstrap_mod.block_bootstrap_pnl

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_same_manifest_yields_same_p5(default_config: BotConfig) -> None:
    """BACK-07: two block_bootstrap_pnl calls with same manifest produce identical p5 estimates."""
    import numpy as np
    from boros_brain.manifest.writer import build_run_manifest

    manifest = build_run_manifest(default_config, parent_run_id=None)
    daily_pnl = np.array([0.01, -0.02, 0.03, 0.005, -0.01, 0.02, 0.01])

    rng1 = make_rng(manifest)
    dist1 = block_bootstrap_pnl(daily_pnl, rng=rng1, n_resamples=200)

    rng2 = make_rng(manifest)
    dist2 = block_bootstrap_pnl(daily_pnl, rng=rng2, n_resamples=200)

    assert np.array_equal(dist1, dist2), (
        f"bootstrap not deterministic: p5(dist1)={np.percentile(dist1, 5):.6f} "
        f"!= p5(dist2)={np.percentile(dist2, 5):.6f}"
    )


def test_seed_from_manifest_is_deterministic(default_config: BotConfig) -> None:
    """BACK-07: seed_from_manifest always returns the same uint64 for the same run_id."""
    from boros_brain.manifest.writer import build_run_manifest

    manifest = build_run_manifest(default_config, parent_run_id=None)
    seed_a = seed_from_manifest(manifest)
    seed_b = seed_from_manifest(manifest)

    assert seed_a == seed_b, f"seed_from_manifest not deterministic: {seed_a} != {seed_b}"
    assert isinstance(seed_a, int)
    assert 0 <= seed_a <= 2**64 - 1


def test_explicit_rng_no_global_state_contamination(default_config: BotConfig) -> None:
    """BACK-07: block_bootstrap_pnl twice in same session → identical results (Pitfall #6 guard).

    Using an explicit RNG derived from the manifest means no global numpy random state
    is consumed, so two sequential calls are reproducible without seeding global state.
    """
    import numpy as np
    from boros_brain.manifest.writer import build_run_manifest

    manifest = build_run_manifest(default_config, parent_run_id=None)
    daily_pnl = np.array([0.01, -0.005, 0.02, -0.01, 0.015, 0.005, -0.003])

    # First call
    rng_a = make_rng(manifest)
    dist_a = block_bootstrap_pnl(daily_pnl, rng=rng_a, n_resamples=100)

    # Second call — same session, should produce same result without global seed
    rng_b = make_rng(manifest)
    dist_b = block_bootstrap_pnl(daily_pnl, rng=rng_b, n_resamples=100)

    assert np.array_equal(dist_a, dist_b), (
        "block_bootstrap_pnl is not reproducible — global numpy state may have been contaminated. "
        "Use explicit RNG derived from manifest."
    )
