"""DECIDE-02 — voluntary_cancel_forfeits_accumulated branch tests (RED until 04-03 lands).

Covers:
  - test_branches_diverge_on_calibrated_scenario (forfeits=False → HOLD, forfeits=True → CANCEL)
  - test_default_branch_is_benign (BotConfig default = False per P0-01)

See: [[Voluntary cancel reward behavior]] — resolved 2026-04-23; flag = False (benign).
EV cancel rule is purely forward-looking; punitive branch = dead-code fallback.

See [[boros-rest-api-margin-endpoint]] and [[phase4-foundation-schema-and-tables]] for Wave-1 foundation.
See [[ev-cancel-rule-implementation-v05]] for the implementation spec.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# RED state guard: modules under test land in Plan 04-03.
engine = pytest.importorskip("boros_brain.decision.engine")
schemas = pytest.importorskip("boros_brain.decision.schemas")
gas_mod = pytest.importorskip("boros_brain.decision.gas_history")

from boros_brain.config.schema import BotConfig  # noqa: E402
from boros_brain.fill_model.schemas import PredictOutput  # noqa: E402

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _patch_config_for_engine(default_config: BotConfig, **extra_overrides) -> BotConfig:
    """Return a config with covariate_whitelist=['basis_spread'] + any extra overrides."""
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("fill_model", {})
    config_dict["fill_model"]["covariate_whitelist"] = ["basis_spread"]
    for k, v in extra_overrides.items():
        parts = k.split(".")
        d = config_dict
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = v
    return BotConfig.model_validate(config_dict)


def _build_eval_input(**overrides):
    defaults = dict(
        market_id=MARKET_ID,
        side="long",
        order_id="test-voluntary-1",
        depth_from_mark_ticks=5,
        queue_ahead_wei=0,
        current_features={"basis_spread": 0.01},  # matches seed_fill_model_fit whitelist
        time_to_epoch_end_s=3600.0,
        time_to_maturity_s=86400 * 30,
        q_me_pendle=2.0,
        sigma_others_pendle=50.0,
        e_liq_per_epoch_pendle=200.0,
        side_split=0.5,
        t_frac=1.0,
        p_purge=0.0,
        r_me_per_epoch_pendle_accumulated_so_far=8.0,  # sunk rewards — key for punitive branch
        current_chain_ts=1_700_000_000,
    )
    defaults.update(overrides)
    return schemas.EvaluateInput(**defaults)


@pytest.mark.parametrize("forfeits", [False, True])
@pytest.mark.asyncio
async def test_branches_diverge_on_calibrated_scenario(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
    seed_fill_model_fit,
    seed_competition_history,
    seed_market_reward_calibration,
    forfeits: bool,
) -> None:
    """DECIDE-02: benign branch (forfeits=False) → HOLD; punitive branch (forfeits=True) → CANCEL.

    Calibration for this test:
      We mock predict() to return p_fill=0.05 exactly so the EV is predictable.
      r_share comes from r_capped_curve with q_me=2, sigma_others=50, e_liq=200:
        r_uncapped = 200 * 0.5 * (2 * 1.0) / (50 + 2) ≈ 3.846 PENDLE
        cap_budget = 10 * 100 * (7/365) / pendle_price_usd ≈ small at pendle=7 → 1.918
        r_share = min(3.846, 1.918) = 1.918 PENDLE (cap-binding)
      e_loss from coarse_bound = 0.02 * 1.0 = 0.02 PENDLE
      cancel_cost = 0 (no w3)
      p_purge = 0

      Benign EV = 1.918 * 0.95 - 0.02 * 0.05 - 0 ≈ 1.822 > 0 → HOLD
      Punitive EV = 1.822 - 8.0 ≈ -6.178 < 0 → CANCEL
    """
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 2.0, 50.0)],
        market_id=MARKET_ID,
    )
    seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 200.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            }
        ]
    )

    # Clone config with the forfeits flag set appropriately.
    config = _patch_config_for_engine(
        default_config,
        **{"strategy.voluntary_cancel_forfeits_accumulated": forfeits},
    )

    # Mock predict to return p_fill=0.05 deterministically for branch isolation
    mock_predict_out = PredictOutput(
        p_fill_this_epoch=0.05,
        lambda_per_second=0.001,
        fit_run_id="mock-fit",
        fit_age_s=0.0,
        fit_status="ok",
    )

    def _mock_predict(*a, **kw):
        return mock_predict_out

    req = _build_eval_input(r_me_per_epoch_pendle_accumulated_so_far=8.0)
    gas_cache = gas_mod.GasHistoryCache()

    with patch("boros_brain.fill_model.predict.predict", _mock_predict):
        out = await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)

    if not forfeits:
        # Benign branch — forward-looking EV > 0 → HOLD
        assert (
            out.decision_kind == "HOLD"
        ), f"benign branch should HOLD but got {out.decision_kind} (ev={out.ev_hold_pendle})"
        assert out.voluntary_cancel_branch == "benign"
    else:
        # Punitive branch — sunk rewards included → CANCEL
        assert (
            out.decision_kind == "CANCEL"
        ), f"punitive branch should CANCEL but got {out.decision_kind} (ev={out.ev_hold_pendle})"
        assert out.voluntary_cancel_branch == "punitive"


@pytest.mark.asyncio
async def test_default_branch_is_benign(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
    seed_fill_model_fit,
) -> None:
    """DECIDE-02: BotConfig() defaults to voluntary_cancel_forfeits_accumulated=False (benign).

    Per P0-01 resolution 2026-04-23 — flag = False is the resolved default.
    [[Voluntary cancel reward behavior]]
    """
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    config = _patch_config_for_engine(default_config)
    req = _build_eval_input()
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(req, sqlite_path=db, config=config, gas_cache=gas_cache, w3=None)
    assert (
        out.voluntary_cancel_branch == "benign"
    ), f"default branch must be benign, got {out.voluntary_cancel_branch!r}"
