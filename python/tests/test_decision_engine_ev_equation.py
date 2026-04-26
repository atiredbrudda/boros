"""DECIDE-01 — engine.evaluate() EV-equation tests (RED until 04-03 lands).

Covers:
  - test_ev_sign_matches_decision (success criterion #1, sign-line-by-line)
  - test_ev_sign_negative_yields_cancel
  - test_ev_monotonicity (hypothesis property — RESEARCH.md §"Composition properties")
  - test_propagates_predict_errors (Pitfall #7 — never swallow)
  - test_propagates_loss_errors

See [[ev-cancel-rule-implementation-v05]] and [[gas-history-ewma-cancel-cost]] for spec.

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
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# RED state guard: module under test lands in Plan 04-03.
# pytest.importorskip causes the entire module to be collected but skipped
# (SKIP status, not ERROR) until boros_brain.decision.engine is implemented.
engine = pytest.importorskip("boros_brain.decision.engine")
schemas = pytest.importorskip("boros_brain.decision.schemas")
gas_mod = pytest.importorskip("boros_brain.decision.gas_history")

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _patch_config_for_engine(default_config: BotConfig) -> BotConfig:
    """Return a config with covariate_whitelist=['basis_spread'] for engine tests.

    The seed_fill_model_fit fixture seeds a fit with covariate_whitelist=['basis_spread'].
    The default config has 5 covariates. We override to a single covariate so
    predict() succeeds when current_features={'basis_spread': 0.01} is passed.

    [Rule 2] Added in Plan 04-03: engine tests need a matching fill model config.
    """
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("fill_model", {})
    config_dict["fill_model"]["covariate_whitelist"] = ["basis_spread"]
    return BotConfig.model_validate(config_dict)


def _build_eval_input(**overrides):
    """Build a minimal EvaluateInput with sensible defaults. Overrides win."""
    defaults = dict(
        market_id=MARKET_ID,
        side="long",
        order_id="test-1",
        depth_from_mark_ticks=5,
        queue_ahead_wei=0,
        current_features={"basis_spread": 0.01},  # matches seed_fill_model_fit whitelist
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
    seed_fill_model_fit,
    seed_competition_history,
    seed_market_reward_calibration,
) -> None:
    """DECIDE-01 success #1: sign-of-EV matches sign-of-decision line-by-line.

    Calibrated for HOLD: r_share≈some positive, p_fill≈low (beta=-2.0+0.1*0.01≈-2),
    e_loss=coarse_bound (empty cells), cancel_cost=0 (no w3) → ev > 0 → HOLD.
    """
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
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
    config = _patch_config_for_engine(default_config)
    req = _build_eval_input(p_purge=0.0)
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)
    assert out.decision_kind == "HOLD"
    assert out.ev_hold_pendle > 0.0


@pytest.mark.asyncio
async def test_ev_sign_negative_yields_cancel(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
    seed_fill_model_fit,
    seed_competition_history,
    seed_market_reward_calibration,
) -> None:
    """DECIDE-01: heavily negative EV → CANCEL decision with ev_hold < 0."""
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
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
    config = _patch_config_for_engine(default_config)
    # r_share tiny (q_me=0.001 → nearly 0 share), p_fill high (deep in money with
    # high sigma), e_loss=coarse_bound → ev < 0 → CANCEL
    req = _build_eval_input(
        q_me_pendle=0.001,
        sigma_others_pendle=0.001,
        e_liq_per_epoch_pendle=0.001,
        current_features={"basis_spread": 100.0},  # very high → high lambda → high p_fill
    )
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)
    assert out.decision_kind == "CANCEL"
    assert out.ev_hold_pendle < 0.0


@given(
    p_fill_q1=st.floats(min_value=0.01, max_value=0.15),
    p_fill_q2=st.floats(min_value=0.50, max_value=0.99),
    r_share_1=st.floats(min_value=0.1, max_value=10.0),
    r_share_2=st.floats(min_value=50.0, max_value=100.0),
)
@settings(max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_ev_monotonicity(
    tmp_path: Path,
    default_config: BotConfig,
    p_fill_q1: float,
    p_fill_q2: float,
    r_share_1: float,
    r_share_2: float,
) -> None:
    """DECIDE-01 property: higher p_fill → lower EV; higher r_share → higher EV.

    Uses asyncio.run since hypothesis doesn't support async fixtures directly.
    Both predict() and expected_loss() are mocked to avoid DB I/O so the test
    can run many iterations without seeding data. The mock patch target must be
    the engine module's imported binding (boros_brain.decision.engine.predict)
    not the original module — since engine.py uses `from ..fill_model.predict import predict`.
    """
    import asyncio
    from unittest.mock import patch

    from boros_brain.fill_model.schemas import PredictOutput
    from boros_brain.loss_model.schemas import ExpectedLossOutput

    gas_cache = gas_mod.GasHistoryCache()
    config = _patch_config_for_engine(default_config)

    # Fixed e_loss so only r_share and p_fill vary across iterations
    mock_loss_out = ExpectedLossOutput(
        expected_loss_pendle=0.5,
        cell_n_samples=10,
        cell_p50_pendle=0.5,
        cell_p95_pendle=1.0,
        fallback_mode="exact",
        grid_artifact_run_id="mock-grid",
        grid_age_s=0.0,
        fit_status="ok",
    )

    def _mock_expected_loss(*a, **kw):
        return mock_loss_out

    async def _run_with_pfill(p_fill_val: float, q_me_pendle: float) -> float:
        mock_predict_out = PredictOutput(
            p_fill_this_epoch=p_fill_val,
            lambda_per_second=1.0,
            fit_run_id="mock-fit",
            fit_age_s=0.0,
            fit_status="ok",
        )

        def _mock_predict(*a, **kw):
            return mock_predict_out

        db = tmp_path / f"state_{p_fill_val:.4f}_{q_me_pendle:.2f}.sqlite"
        req = _build_eval_input(
            q_me_pendle=q_me_pendle,
            sigma_others_pendle=100.0,
            e_liq_per_epoch_pendle=q_me_pendle * 10,
            p_purge=0.0,
        )
        # Patch engine's local binding of predict and expected_loss (not source module)
        with (
            patch("boros_brain.decision.engine.predict", _mock_predict),
            patch("boros_brain.decision.engine.expected_loss", _mock_expected_loss),
        ):
            out = await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)
        return out.ev_hold_pendle

    ev_low_pfill = asyncio.run(_run_with_pfill(p_fill_q1, r_share_1))
    ev_high_pfill = asyncio.run(_run_with_pfill(p_fill_q2, r_share_1))
    # Higher p_fill → lower EV (monotone)
    assert (
        ev_low_pfill >= ev_high_pfill - 1e-9
    ), f"p_fill monotonicity violated: ev({p_fill_q1})={ev_low_pfill} < ev({p_fill_q2})={ev_high_pfill}"

    ev_low_rshare = asyncio.run(_run_with_pfill(p_fill_q1, r_share_1))
    ev_high_rshare = asyncio.run(_run_with_pfill(p_fill_q1, r_share_2))
    # Higher r_share → higher EV
    assert (
        ev_high_rshare >= ev_low_rshare - 1e-9
    ), f"r_share monotonicity violated: ev({r_share_2})={ev_high_rshare} < ev({r_share_1})={ev_low_rshare}"


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
        raise FillModelStaleFeatureError(missing_features=["basis_spread"])

    # Patch engine's local binding — engine.py uses `from ..fill_model.predict import predict`
    monkeypatch.setattr("boros_brain.decision.engine.predict", _raise)
    config = _patch_config_for_engine(default_config)
    req = _build_eval_input()
    gas_cache = gas_mod.GasHistoryCache()
    with pytest.raises(FillModelStaleFeatureError):
        await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)


@pytest.mark.asyncio
async def test_propagates_loss_errors(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch,
    seed_loss_grid_artifact,
) -> None:
    """DECIDE-01 Pitfall #7 — engine NEVER swallows loss model errors.

    LossModelNoFreshGridError must propagate to the caller unchanged.
    predict() is also mocked so it succeeds, allowing the loss error to propagate.
    """
    from boros_brain.fill_model.schemas import PredictOutput
    from boros_brain.loss_model.expected_loss import LossModelNoFreshGridError

    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    def _raise_loss(*a, **kw):
        raise LossModelNoFreshGridError("no fresh grid")

    # Predict must succeed so the loss error reaches the caller
    _ok_predict = PredictOutput(
        p_fill_this_epoch=0.1,
        lambda_per_second=0.001,
        fit_run_id="mock",
        fit_age_s=0.0,
        fit_status="ok",
    )

    def _mock_predict(*a, **kw):
        return _ok_predict

    # Patch engine's local bindings
    monkeypatch.setattr("boros_brain.decision.engine.predict", _mock_predict)
    monkeypatch.setattr("boros_brain.decision.engine.expected_loss", _raise_loss)
    config = _patch_config_for_engine(default_config)
    req = _build_eval_input()
    gas_cache = gas_mod.GasHistoryCache()
    with pytest.raises(LossModelNoFreshGridError):
        await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)
