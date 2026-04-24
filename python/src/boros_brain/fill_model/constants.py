"""Fill-model covariate whitelist + default windowing constants.

No functions (public_functions=[] in architecture.yml).
All constants are module-level only — no top-level `def`.

[[covariate-selection-v05]]: 4 covariates → 5 model features selected for v0.5.
"""

from __future__ import annotations

ALLOWED_COVARIATES: frozenset[str] = frozenset(
    {
        "basis_spread",
        "imbalance",
        "sin_settlement",
        "cos_settlement",
        "ewma_vol",
    }
)

DEFAULT_BIN_DURATION_S: float = 60.0
DEFAULT_WINDOW_DAYS: int = 14
DEFAULT_REFIT_CADENCE_S: float = 900.0
DEFAULT_COVARIATE_WHITELIST: list[str] = [
    "basis_spread",
    "imbalance",
    "sin_settlement",
    "cos_settlement",
    "ewma_vol",
]
