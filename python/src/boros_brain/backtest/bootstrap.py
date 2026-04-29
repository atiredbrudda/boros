"""BACK-07: block-bootstrap evaluator. RNG seeded from RUN_MANIFEST for reproducibility.

Block bootstrap with block_seconds=86400 (1 day) preserves intra-day P&L autocorrelation.
N=2000 resamples gives MC error ~1.5% on the 5th percentile (binomial CI).

PITFALL #6 (Phase-5 NEW): NEVER call top-level numpy.random.* — always pass an explicit
Generator instance. RNG state contamination kills idempotence.

[[backtest-bootstrap-methodology-v05]]
[[backtest-reproducibility-rng-seed-from-manifest]]
"""

from __future__ import annotations

import numpy as np
import structlog
import ulid

from ..manifest.schema import RunManifest

log = structlog.get_logger(__name__)


def seed_from_manifest(manifest: RunManifest) -> int:
    """ULID -> uint64 seed. Idempotent: same manifest -> same seed.

    ULID is 26-char Crockford base32 (128 bits). Take the low 64 bits of the byte
    representation as the seed.
    """
    u = ulid.ULID.from_str(manifest.run_id)
    return int.from_bytes(u.bytes[-8:], byteorder="big") & ((1 << 64) - 1)


def make_rng(manifest: RunManifest) -> np.random.Generator:
    """Construct a fresh Generator seeded from the manifest. Pass explicitly to bootstrap."""
    return np.random.default_rng(seed_from_manifest(manifest))


def block_bootstrap_pnl(
    daily_pnl: np.ndarray,
    *,
    rng: np.random.Generator,
    n_resamples: int = 2000,
) -> np.ndarray:
    """Returns N annualized P&L values resampled with replacement on day-blocks.

    Unit contract (load-bearing — see [[ship-gate-units-bug-2026-04-30]]):
      `daily_pnl[i]` MUST be a daily fraction of USD collateral (i.e., daily-USD-APR
      already normalized by capital). Producer: replay._aggregate_daily_pnl. With
      that contract, `sample.sum() × 365 / n_days` returns a USD-APR fraction
      directly comparable to `screener.alt_yield + backtest.all_fees_threshold`.

      Passing raw PENDLE/day (or any unnormalized quantity) silently produces a
      number with the wrong unit; the verdict comparison in evaluate_ship_gate
      will be unit-incoherent. The replay path enforces the contract; tests that
      hand-craft daily_pnl arrays must do the same (see test_backtest_ship_gate_*).

    Resampling: rng.choice(daily_pnl, size=n_days, replace=True) per resample.
    Annualization: sum_resampled * (365.0 / n_days).

    PITFALL #6: rng MUST be an explicit Generator — never use top-level numpy.random.
    """
    n_days = len(daily_pnl)
    if n_days == 0:
        raise ValueError("daily_pnl is empty; cannot bootstrap")
    out = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        sample = rng.choice(daily_pnl, size=n_days, replace=True)
        out[i] = sample.sum() * (365.0 / n_days)
    return out


__all__ = ["seed_from_manifest", "make_rng", "block_bootstrap_pnl"]
