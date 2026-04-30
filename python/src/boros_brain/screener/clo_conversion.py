"""Phase 05.3 Plan 01 D2 — single source of truth for CLO fIndex→tick conversion.

Lifted from ``screener/filter.py:_clo_findex_to_tick`` so that both the
screener (DATA-08 filter pipeline) and the backtest replay engine
(``backtest/replay.py``) consume the same conversion. Pre-T3 the helper was
inlined in ``screener/filter.py`` with module-level SCALE/S/TICK_SIZE
defaults; the screener used it via ``apply_screener_filters`` and replay
duplicated the math via ``int(market.clo_lower_thresh)`` (broken — fIndex
display units treated as a tick) and ``float(market.clo_lower_thresh) /
10_000.0`` (broken — same display value pseudo-rescaled to a "rate
fraction"). The fill-path repair plan (D2) lifts the helper here so both
call sites import the same function.

The post-lift signature accepts an optional ``scale`` kwarg so callers with
per-market calibration (e.g. backtest with the binding-market ``scale =
606985714285.0`` from the strategy YAML) can override the screener's
``_CLO_SCALE_DEFAULT`` (calibrated for the 29MAY2026 market). Default
behavior is unchanged for the screener — passing only the original three
positional args yields the same tick value as the pre-lift helper.

Wiki: [[fill-path-repair-2026-04-30]]
"""

from __future__ import annotations

import math

# ── CLO fIndex→APR→tick conversion defaults ──────────────────────────────────
# cloLowerThresh / cloUpperThresh in clo_history are in fIndex display units
# (NOT integer tick indices). Converting to the order-book tick grid requires:
#   fIndex_display = 10000 + f_index_raw / SCALE
#   APR = (cloThresh - fIndex_display) / timeToMaturity_years / S
#   tick = round(APR / TICK_SIZE)
#
# SCALE and S are calibrated per market (boros_bot_guide.md §ETHUSDT calibration:
#   SCALE ≈ 5.591e12, S ≈ 402648 for ETHUSDT Binance). When only one
# clo_history observation is available (Wave-1 single UAT snapshot) the two-point
# calibration in scale_calibration.py raises InsufficientCalibrationData, so we
# fall back to the ETHUSDT-derived defaults. These defaults are coarse for
# non-ETHUSDT markets but are better than always returning None from Filter 4.
# TODO(Phase-7): replace defaults with per-market SCALE/S sourced from operator
#     calibration CLI once two or more clo_history observations per market exist.
_CLO_SCALE_DEFAULT: float = 5.591e12  # boros_bot_guide.md §L508: SCALE for ETHUSDT
_CLO_S_DEFAULT: float = 402_648.0  # boros_bot_guide.md §L509: S for ETHUSDT APR formula
_CLO_TICK_SIZE_DEFAULT: float = 0.01  # All Wave-1 markets use 0.01 tick_size


def clo_findex_to_tick(
    clo_thresh: float,
    f_index_raw: int | None,
    ttm_days: float,
    *,
    scale: float | None = None,
    s: float | None = None,
    tick_size: float | None = None,
) -> int | None:
    """Convert a CLO threshold (fIndex display units) to an order-book tick integer.

    Formula (boros_bot_guide.md §"Converting CLO Values to APR")::

        fIndex_display = 10000 + f_index_raw / SCALE
        APR = (clo_thresh - fIndex_display) / timeToMaturity_years / S
        tick = round(APR / TICK_SIZE)

    Falls back to ``_CLO_SCALE_DEFAULT`` / ``_CLO_S_DEFAULT`` /
    ``_CLO_TICK_SIZE_DEFAULT`` when the corresponding kwarg is None or
    falsy. Per-market calibration overrides those defaults when supplied.

    Returns ``None`` when:
    - ``f_index_raw`` is None (column missing or null in old schema rows).
    - ``ttm_days`` <= 0 (market already expired or no TTM data).
    - Computed APR is non-finite (overflow / NaN guard).

    Phase 05.3 D2 single source of truth — both ``screener/filter.py`` and
    ``backtest/replay.py`` import this function. See
    [[fill-path-repair-2026-04-30]].
    """
    if f_index_raw is None or ttm_days <= 0:
        return None

    effective_scale = float(scale) if scale else _CLO_SCALE_DEFAULT
    effective_s = float(s) if s else _CLO_S_DEFAULT
    effective_tick_size = float(tick_size) if tick_size else _CLO_TICK_SIZE_DEFAULT

    ttm_years = ttm_days / 365.0
    findex_display = 10000.0 + f_index_raw / effective_scale
    apr = (clo_thresh - findex_display) / ttm_years / effective_s
    if not math.isfinite(apr):
        return None
    return round(apr / effective_tick_size)


__all__ = [
    "clo_findex_to_tick",
    "_CLO_SCALE_DEFAULT",
    "_CLO_S_DEFAULT",
    "_CLO_TICK_SIZE_DEFAULT",
]
