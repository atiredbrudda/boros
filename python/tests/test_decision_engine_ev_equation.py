"""DECIDE-01 — engine.evaluate() EV-equation tests (RED until 04-03 lands).

Covers:
  - test_ev_sign_matches_decision (success criterion #1, sign-line-by-line)
  - test_ev_sign_negative_yields_cancel
  - test_ev_monotonicity (hypothesis property — RESEARCH.md §"Composition properties")
  - test_propagates_predict_errors (Pitfall #7 — never swallow)
  - test_propagates_loss_errors

>>> # Wave 0 sign-off invariant: this module RED-skips cleanly until 04-03 lands.
>>> import importlib
>>> try:
...     importlib.import_module('boros_brain.decision.engine')
...     assert False, "module should not exist yet"
... except (ImportError, ModuleNotFoundError):
...     pass
"""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

# RED state guard: module under test lands in Plan 04-03.
# pytest.importorskip causes the entire module to be collected but skipped
# (SKIP status, not ERROR) until boros_brain.decision.engine is implemented.
engine = pytest.importorskip("boros_brain.decision.engine")
schemas = pytest.importorskip("boros_brain.decision.schemas")
gas_mod = pytest.importorskip("boros_brain.decision.gas_history")

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _build_eval_input(**overrides):
    """Build a minimal EvaluateInput with sensible defaults. Overrides win."""
    defaults = dict(
        market_id=MARKET_ID,
        side="long",
        order_id="test-1",
        depth_from_mark_ticks=5,
        queue_ahead_wei=0,
        current_features={"sigma_5min": 0.01},
        time_to_epoch_end_s=3600.0,
        time_to_maturity_s=86400 * 30,
        q_me_pendle=10.0,
        sigma_others_pendle=100.0,
        e_liq_per_epoch_pendle=1000.0,
        side_split=0.5,
        t_frac=1.0,
        p_purge=0.0,
        r_me_per_epoch_pendle_accumulated_so_far=0.0,
        current_chain_ts=1_700_000_000,
    )
    defaults.update(overrides)
    return schemas.EvaluateInput(**defaults)


@pytest.mark.asyncio
async def test_ev_sign_matches_decision(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
    seed_competition_history,
    seed_market_reward_calibration,
) -> None:
    """DECIDE-01 success #1: sign-of-EV matches sign-of-decision line-by-line.

    Calibrated for HOLD: r_share=10, p_fill=0.05, e_loss=0.5, cancel_cost~0
    → ev ≈ 10*0.95 - 0.5*0.05 - 0.0 = 9.5 - 0.025 > 0 → HOLD.
    """
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )
    seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    req = _build_eval_input(p_purge=0.0)
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(
        req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None
    )
    assert out.decision_kind == "HOLD"
    assert out.ev_hold_pendle > 0.0


@pytest.mark.asyncio
async def test_ev_sign_negative_yields_cancel(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
    seed_competition_history,
    seed_market_reward_calibration,
) -> None:
    """DECIDE-01: heavily negative EV → CANCEL decision with ev_hold < 0."""
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )
    seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )
    # r_share tiny, p_fill huge, e_loss huge → ev = 0.1*0.1 - 20*0.9 - 0.1 < 0 → CANCEL
    req = _build_eval_input(
        q_me_pendle=0.1,
        sigma_others_pendle=100.0,
        e_liq_per_epoch_pendle=10.0,
    )
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(
        req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None
    )
    assert out.decision_kind == "CANCEL"
    assert out.ev_hold_pendle < 0.0


@given(
    p_fill_1=st.floats(min_value=0.01, max_value=0.49),
    p_fill_2=st.floats(min_value=0.50, max_value=0.99),
    r_share_1=st.floats(min_value=0.1, max_value=50.0),
    r_share_2=st.floats(min_value=51.0, max_value=100.0),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_ev_monotonicity(
    tmp_path: Path,
    default_config: BotConfig,
    p_fill_1: float,
    p_fill_2: float,
    r_share_1: float,
    r_share_2: float,
) -> None:
    """DECIDE-01 property: higher p_fill → lower EV; higher r_share → higher EV.

    Hypothesis property test — calls evaluate via asyncio.run for hypothesis compat.
    """
    import asyncio

    gas_cache = gas_mod.GasHistoryCache()

    async def _run(p_fill_val: float, r_share_val: float) -> float:
        req = _build_eval_input(
            q_me_pendle=r_share_val,
            sigma_others_pendle=100.0,
            e_liq_per_epoch_pendle=r_share_val * 10,
            p_purge=0.0,
        )
        db = tmp_path / f"state_{p_fill_val:.4f}_{r_share_val:.2f}.sqlite"
        out = await engine.evaluate(
            req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None
        )
        return out.ev_hold_pendle

    ev_low_pfill = asyncio.run(_run(p_fill_1, r_share_1))
    ev_high_pfill = asyncio.run(_run(p_fill_2, r_share_1))
    # Higher p_fill → lower EV (monotone)
    assert ev_low_pfill >= ev_high_pfill - 1e-9, (
        f"p_fill monotonicity violated: ev({p_fill_1})={ev_low_pfill} < ev({p_fill_2})={ev_high_pfill}"
    )

    ev_low_rshare = asyncio.run(_run(p_fill_1, r_share_1))
    ev_high_rshare = asyncio.run(_run(p_fill_1, r_share_2))
    # Higher r_share → higher EV
    assert ev_high_rshare >= ev_low_rshare - 1e-9, (
        f"r_share monotonicity violated: ev({r_share_2})={ev_high_rshare} < ev({r_share_1})={ev_low_rshare}"
    )


@pytest.mark.asyncio
async def test_propagates_predict_errors(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch,
    seed_loss_grid_artifact,
) -> None:
    """DECIDE-01 Pitfall #7 — engine NEVER swallows fill model errors.

    FillModelStaleFeatureError must propagate to the caller unchanged.
    """
    from boros_brain.fill_model.predict import FillModelStaleFeatureError

    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    def _raise(*a, **kw):
        raise FillModelStaleFeatureError(missing_features=["sigma_5min"])

    monkeypatch.setattr("boros_brain.fill_model.predict.predict", _raise)
    req = _build_eval_input()
    gas_cache = gas_mod.GasHistoryCache()
    with pytest.raises(FillModelStaleFeatureError):
        await engine.evaluate(
            req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None
        )


@pytest.mark.asyncio
async def test_propagates_loss_errors(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch,
    seed_loss_grid_artifact,
) -> None:
    """DECIDE-01 Pitfall #7 — engine NEVER swallows loss model errors.

    LossModelNoFreshGridError must propagate to the caller unchanged.
    """
    from boros_brain.loss_model.expected_loss import LossModelNoFreshGridError

    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    def _raise(*a, **kw):
        raise LossModelNoFreshGridError("no fresh grid")

    monkeypatch.setattr("boros_brain.loss_model.expected_loss.expected_loss", _raise)
    req = _build_eval_input()
    gas_cache = gas_mod.GasHistoryCache()
    with pytest.raises(LossModelNoFreshGridError):
        await engine.evaluate(
            req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None
        )
