"""Deterministic generator for fill_model_synthetic_poisson.parquet + fill_model_regime_shift.parquet.

This script is the SSoT; committed parquet files are artifacts derived from running it.
Regenerate with: ``uv run python python/tests/fixtures/_generate_fill_model_fixtures.py``

Seed = 42 (fixed for deterministic outputs).

Design:
- synthetic_poisson: 2000 bins, known β_true, trade_count ~ Poisson(λ × 60s).
  Used by test_fit_converges_on_synthetic_poisson (T-02-M-01): fit should recover β_true
  within ~3 standard errors on each parameter.
- regime_shift: same structure but two regimes (bins 0..1399 / 1400..1999).
  Used by test_degraded_warning_on_regime_shift (T-02-C-03): GoF degrades when
  post-regime data is scored against the pre-regime model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

FIXTURE_DIR = Path(__file__).parent

# True coefficients for the synthetic Poisson fixture.
# Intercept + 5 covariate coefficients (basis_spread, imbalance, sin_settlement,
# cos_settlement, ewma_vol) — matching ALLOWED_COVARIATES in fill_model.constants.
BETA_TRUE = np.array([-1.0, 0.5, -0.3, 0.1, 0.1, 0.2])  # shape (6,)

BETA_REGIME1 = np.array([-1.0, 0.5, -0.3, 0.1, 0.1, 0.2])
BETA_REGIME2 = np.array([-1.0, -0.5, -0.3, 0.1, 0.1, 0.2])  # basis_spread sign flipped


def _sample_features(rng: np.random.Generator, n: int) -> np.ndarray:
    """Sample n rows of 5 covariates from standard normal. Shape: (n, 5)."""
    return rng.standard_normal((n, 5))


def _compute_lambda(beta: np.ndarray, X: np.ndarray, bin_duration_s: float = 60.0) -> np.ndarray:
    """Compute expected trade count per bin: λ = exp(β₀ + X·β[1:]) × bin_duration_s."""
    eta = beta[0] + X @ beta[1:]
    return np.exp(eta) * bin_duration_s


def generate_synthetic_poisson(out_path: Path, rng: np.random.Generator) -> None:
    """Generate 2000-bin fixture with known-β Poisson trade counts."""
    n = 2000
    X = _sample_features(rng, n)
    lam = _compute_lambda(BETA_TRUE, X)
    trade_count = rng.poisson(lam).astype(np.int32)

    df = pl.DataFrame(
        {
            "bin_start": np.arange(n, dtype=np.int64) * 60,
            "market_id": ["BINANCE-ETHUSDT-TEST"] * n,
            "side": ["long"] * n,
            "trade_count": trade_count.tolist(),
            "basis_spread": X[:, 0].tolist(),
            "imbalance": X[:, 1].tolist(),
            "sin_settlement": X[:, 2].tolist(),
            "cos_settlement": X[:, 3].tolist(),
            "ewma_vol": X[:, 4].tolist(),
            "bin_duration_s": [60.0] * n,
        }
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(str(out_path))
    print(f"wrote {out_path} ({n} rows, beta_true={BETA_TRUE.tolist()})")


def generate_regime_shift(out_path: Path, rng: np.random.Generator) -> None:
    """Generate 2000-bin fixture with a regime change at bin 1400.

    Bins 0..1399 use BETA_REGIME1 (basis_spread coeff = +0.5).
    Bins 1400..1999 use BETA_REGIME2 (basis_spread coeff = -0.5).
    The sign flip on basis_spread creates a detectable regime shift for the GoF test.
    """
    n = 2000
    split = 1400

    X = _sample_features(rng, n)

    lam1 = _compute_lambda(BETA_REGIME1, X[:split])
    lam2 = _compute_lambda(BETA_REGIME2, X[split:])
    lam = np.concatenate([lam1, lam2])

    trade_count = rng.poisson(lam).astype(np.int32)

    regime = ["regime1"] * split + ["regime2"] * (n - split)

    df = pl.DataFrame(
        {
            "bin_start": np.arange(n, dtype=np.int64) * 60,
            "market_id": ["BINANCE-ETHUSDT-TEST"] * n,
            "side": ["long"] * n,
            "trade_count": trade_count.tolist(),
            "basis_spread": X[:, 0].tolist(),
            "imbalance": X[:, 1].tolist(),
            "sin_settlement": X[:, 2].tolist(),
            "cos_settlement": X[:, 3].tolist(),
            "ewma_vol": X[:, 4].tolist(),
            "bin_duration_s": [60.0] * n,
            "regime": regime,
        }
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(str(out_path))
    print(f"wrote {out_path} ({n} rows, regime1={BETA_REGIME1.tolist()}, regime2={BETA_REGIME2.tolist()})")


def main() -> None:
    """Regenerate both fixture parquet files deterministically (seed=42)."""
    rng = np.random.default_rng(42)
    generate_synthetic_poisson(FIXTURE_DIR / "fill_model_synthetic_poisson.parquet", rng)
    generate_regime_shift(FIXTURE_DIR / "fill_model_regime_shift.parquet", rng)
    print("regenerated")


if __name__ == "__main__":
    main()
