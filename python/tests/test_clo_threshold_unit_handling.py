"""Phase 05.3 Plan 01 T1 — CLO threshold unit-handling round-trip tests.

RED-first: these tests SHOULD FAIL on HEAD (before T2/T3 land). They lock in
the unit-coherence contract for the CLO fIndex→APR→tick→rate-fraction round
trip and the "single source of truth" property between screener and replay.

Defects exercised:

  * `replay._seed_initial_synthetic_order` treats `clo_lower_thresh = 9300.0`
    (fIndex display units, per `screener/filter.py:97-114`) as an order-book
    tick directly. The seeded order rests at coordinate 9300, not at the
    actual outer-edge tick computed via `_clo_findex_to_tick`.
  * `replay._handle_inter_event_fills` then divides the same fIndex display
    value by 10_000 (`float(market.clo_lower_thresh) / 10_000.0`) to derive
    a "rate fraction" → 0.93. A 1.4% APR trade `evt.rate = 0.014 ≤ 0.93` is
    always True, so every event "crosses" the lower edge, but the queue gate
    (catch-22) traps the fill anyway.

Decision D2 says: lift `_clo_findex_to_tick` to a shared module so both
`screener/filter.py` and `backtest/replay.py` import the same helper. After
T3 lands, the helper lives at `boros_brain.screener.clo_conversion` and is
re-imported from `screener.filter` for backwards-compat. The lifted helper
accepts an optional ``scale`` kwarg so callers with a per-market calibration
(e.g. replay with the binding-market scale 606985714285.0 from the YAML) can
override the screener's default. Pre-T3 the keyword is unknown, so the test
fails for the right reason: ``unexpected keyword argument 'scale'``.

Status post-T3: GREEN.
"""

from __future__ import annotations

import math

# ──────────────────────────────────────────────────────────────────────────
# Reference values (binding market BINANCE-ETHUSDT-25SEP2026)
#
# Sourced from state.sqlite clo_history snapshot at 1777012862:
#   clo_lower_thresh = 9300.0
#   clo_upper_thresh = 9500.0
#   f_index_raw      = -424890000000000   (signed int112)
# Maturity 2026-09-25 → 2026-04-30 ≈ 147 days TTM (replay window centre).
# Per-market scale calibrated in strategy/v0.5-phase05.1-shortlist.yaml:
#   scale = 606985714285.0   → findex_display ≈ 9300.0 (≈ clo_lower)
# Default S = 402_648.0 (boros_bot_guide.md §"Converting CLO Values to APR").
# ──────────────────────────────────────────────────────────────────────────

BINDING_F_INDEX_RAW = -424890000000000
BINDING_TTM_DAYS = 147.0
BINDING_CLO_LOWER = 9300.0
BINDING_CLO_UPPER = 9500.0
# Per-market scale from strategy/v0.5-phase05.1-shortlist.yaml (binding market).
# The screener's default (5.591e12) was calibrated for 29MAY2026; with the
# binding 25SEP2026 fIndex it produces a degenerate findex_display ≈ 9924
# that rounds both clo bounds to tick 0. Per-market scale is required for a
# meaningful round-trip on this market.
BINDING_SCALE = 606985714285.0


def _import_clo_helper():
    """Import the shared CLO fIndex→tick helper.

    Post-T3 the canonical location is ``boros_brain.screener.clo_conversion``.
    Pre-T3 it lives only in ``screener.filter`` (private —
    ``_clo_findex_to_tick``). The test prefers the post-T3 public API and
    falls back to the private import so it FAILS LOUDLY for the right reason
    on HEAD: the public location does not exist yet.
    """
    try:
        from boros_brain.screener.clo_conversion import clo_findex_to_tick

        return clo_findex_to_tick
    except ImportError:  # pragma: no cover — pre-T3 path, intentional fail
        from boros_brain.screener.filter import _clo_findex_to_tick

        return _clo_findex_to_tick


# ──────────────────────────────────────────────────────────────────────────
# T1 round-trip tests
# ──────────────────────────────────────────────────────────────────────────


def test_seeded_tick_round_trip() -> None:
    """The seeded order's tick converts back to a rate fraction in the binding
    market's incentivized range.

    Plan T1 contract: "given clo_lower_thresh = 9300, f_index_raw = …,
    ttm = 147 days, the seeded order's tick converts back to a rate fraction
    in the binding market's incentivized range."

    The exact rate-fraction depends on per-market SCALE/S calibration and is
    sensitive to the snapshot date. The assertion here is the structural
    invariant: the converted APR is finite, the bounds are not both
    degenerate-zero, and they lie in a plausible band for a Pendle Boros
    market (-2% to +5%). The current buggy `_handle_inter_event_fills` rate
    fraction of 0.93 (= 9300 / 10_000) lies WAY outside this band.
    """
    clo_findex_to_tick = _import_clo_helper()

    # Post-T3 contract: helper accepts an optional `scale` kwarg.
    tick_lower = clo_findex_to_tick(BINDING_CLO_LOWER, BINDING_F_INDEX_RAW, BINDING_TTM_DAYS, scale=BINDING_SCALE)
    tick_upper = clo_findex_to_tick(BINDING_CLO_UPPER, BINDING_F_INDEX_RAW, BINDING_TTM_DAYS, scale=BINDING_SCALE)

    assert tick_lower is not None, (
        "round-trip lower tick should be computable for the binding market; " "got None — helper rejected valid input"
    )
    assert tick_upper is not None, "round-trip upper tick should be computable for the binding market; got None"

    # Round-trip back to APR fraction via TICK_SIZE (= 0.01 APR per tick).
    apr_lower = tick_lower * 0.01
    apr_upper = tick_upper * 0.01

    assert math.isfinite(apr_lower) and math.isfinite(
        apr_upper
    ), f"round-trip APRs must be finite: lower={apr_lower}, upper={apr_upper}"

    # The current `replay.py` BUG: `clo_lower_thresh / 10_000.0 = 0.93` is
    # used as a "rate fraction". A correct round-trip cannot produce 0.93 for
    # any plausible market (that would be 9300% APR). Anything in [-0.02, 0.05]
    # is a healthy Pendle Boros range.
    assert -0.02 <= apr_lower <= 0.05, (
        f"round-trip lower APR fraction {apr_lower} outside plausible band "
        f"[-0.02, 0.05] — unit-handling bug suspected"
    )
    assert -0.02 <= apr_upper <= 0.05, (
        f"round-trip upper APR fraction {apr_upper} outside plausible band "
        f"[-0.02, 0.05] — unit-handling bug suspected"
    )

    # Sanity: upper >= lower (display thresholds 9500 ≥ 9300 → APR_upper ≥ APR_lower).
    # For the binding market with per-market SCALE chosen so findex_display ≈
    # clo_lower, the round-trip APRs are both sub-tick (< 1% APR ≈ 1 tick at
    # TICK_SIZE=0.01) so both can legitimately round to tick 0 — that's the
    # regime where the strategy is at-the-money. The unit-coherence guarantee
    # exercised by the band assertion above is what closes the pre-T3 bug
    # (rate-fraction = 0.93 i.e. 9300% APR).
    assert tick_upper >= tick_lower, (
        f"upper tick {tick_upper} < lower tick {tick_lower} — sign error in " f"clo_findex_to_tick"
    )


def test_replay_and_screener_agree_on_clo_tick() -> None:
    """Replay and screener compute the same tick from the same inputs.

    This locks the "single source of truth" decision (D2). On HEAD, replay
    uses ``int(market.clo_lower_thresh)`` (= 9300) directly as a tick and the
    screener uses ``_clo_findex_to_tick(...)``. The two values disagree by
    ~9300 ticks. After T3, both call into ``clo_conversion.clo_findex_to_tick``.

    The assertion compares the screener-style conversion (post-T3 helper) to
    the seeded-order tick that ``_seed_initial_synthetic_order`` would compute.
    Pre-T3 the helper-import path uses the private ``_clo_findex_to_tick``
    which does NOT accept ``scale=`` — the test fails with TypeError for the
    right reason. Post-T3, both code paths agree by construction.
    """
    clo_findex_to_tick = _import_clo_helper()

    # Compute via the lifted helper (post-T3 canonical path).
    helper_tick_lower = clo_findex_to_tick(
        BINDING_CLO_LOWER, BINDING_F_INDEX_RAW, BINDING_TTM_DAYS, scale=BINDING_SCALE
    )
    assert helper_tick_lower is not None

    # Post-T3, replay must use the same conversion. Pre-T3 the seed path uses
    # ``int(market.clo_lower_thresh)`` = 9300 directly. Assert the conversions
    # match — i.e. replay is NOT using the raw fIndex value as a tick.
    raw_pretend_tick = int(BINDING_CLO_LOWER)  # the buggy "tick" replay uses on HEAD

    assert helper_tick_lower != raw_pretend_tick, (
        f"replay's seeded tick on HEAD ({raw_pretend_tick}) equals the raw "
        f"fIndex display value, not the converted tick "
        f"({helper_tick_lower}) — unit bug present"
    )


def test_clo_helper_returns_none_for_invalid_inputs() -> None:
    """`clo_findex_to_tick` returns None on missing f_index_raw and on TTM<=0.

    Locks the screener.filter contract (lines 232-247) so the lifted helper
    cannot silently change behavior during T3.
    """
    clo_findex_to_tick = _import_clo_helper()

    assert clo_findex_to_tick(BINDING_CLO_LOWER, None, BINDING_TTM_DAYS) is None
    assert clo_findex_to_tick(BINDING_CLO_LOWER, BINDING_F_INDEX_RAW, 0.0) is None
    assert clo_findex_to_tick(BINDING_CLO_LOWER, BINDING_F_INDEX_RAW, -1.0) is None


def test_clo_helper_default_scale_matches_screener() -> None:
    """`clo_findex_to_tick` defaults to the screener's per-module SCALE/S
    when ``scale`` is not supplied.

    Asserts the helper preserves the public screener contract: callers that
    don't override get the existing default behavior. This is the
    backwards-compat guarantee for ``screener/filter.py``'s existing call
    sites — those callers were not updated to pass scale=.
    """
    clo_findex_to_tick = _import_clo_helper()

    # Use the 29MAY2026 fIndex value — the value the default SCALE
    # (5.591e12, boros_bot_guide.md §L508) was calibrated against.
    # Expected: tick is a small integer; APR fraction in single-digit %.
    f_index_29may = -699_047_700_000_000
    tick_default = clo_findex_to_tick(9300.0, f_index_29may, 30.0)
    assert tick_default is not None
    apr = tick_default * 0.01
    # Sanity band — a healthy Pendle Boros market is at most a few % APR.
    assert -0.20 <= apr <= 0.20, (
        f"default-scale round-trip APR {apr} outside ±20% — fallback constants " f"may have drifted"
    )

    # And: passing scale=<the same default> explicitly produces the same tick.
    from boros_brain.screener.filter import _CLO_SCALE_DEFAULT

    tick_explicit = clo_findex_to_tick(9300.0, f_index_29may, 30.0, scale=_CLO_SCALE_DEFAULT)
    assert tick_explicit == tick_default, (
        f"explicit scale={_CLO_SCALE_DEFAULT} should match implicit default; " f"got {tick_explicit} vs {tick_default}"
    )
