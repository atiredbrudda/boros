"""DECIDE-02 — voluntary_cancel_forfeits_accumulated branch tests (RED until 04-03 lands).

Covers:
  - test_branches_diverge_on_calibrated_scenario (forfeits=False → HOLD, forfeits=True → CANCEL)
  - test_default_branch_is_benign (BotConfig default = False per P0-01)

See: [[Voluntary cancel reward behavior]] — resolved 2026-04-23; flag = False (benign).
EV cancel rule is purely forward-looking; punitive branch = dead-code fallback.

See [[boros-rest-api-margin-endpoint]] and [[phase4-foundation-schema-and-tables]] for Wave-1 foundation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: modules under test land in Plan 04-03.
engine = pytest.importorskip("boros_brain.decision.engine")
schemas = pytest.importorskip("boros_brain.decision.schemas")
gas_mod = pytest.importorskip("boros_brain.decision.gas_history")

from boros_brain.config.schema import BotConfig  # noqa: E402

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _build_eval_input(**overrides):
    defaults = dict(
        market_id=MARKET_ID,
        side="long",
        order_id="test-voluntary-1",
        depth_from_mark_ticks=5,
        queue_ahead_wei=0,
        current_features={"sigma_5min": 0.01},
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
    seed_competition_history,
    seed_market_reward_calibration,
    forfeits: bool,
) -> None:
    """DECIDE-02: benign branch (forfeits=False) → HOLD; punitive branch (forfeits=True) → CANCEL.

    Calibration:
      r_share = 2 PENDLE (current epoch forward-looking)
      p_fill  = 0.05 (low)
      e_loss  = 20 PENDLE (high — position is close to market)
      sunk    = 8 PENDLE accumulated so far

    Benign (forward-looking only):
      ev = 2*0.95 - 20*0.05 - 0 = 1.9 - 1.0 = 0.9 > 0 → HOLD

    Punitive (sunk included in forfeit):
      ev_punitive = ev_benign - sunk*P(voluntary_cancel) < 0 → CANCEL
    """
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
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
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("strategy", {})
    config_dict["strategy"]["voluntary_cancel_forfeits_accumulated"] = forfeits
    patched_config = BotConfig.model_validate(config_dict)

    req = _build_eval_input(r_me_per_epoch_pendle_accumulated_so_far=8.0)
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(
        req, sqlite_path=db, config=patched_config, gas_cache=gas_cache, w3=None
    )

    if not forfeits:
        # Benign branch — forward-looking EV > 0 → HOLD
        assert out.decision_kind == "HOLD", (
            f"benign branch should HOLD but got {out.decision_kind} (ev={out.ev_hold_pendle})"
        )
        assert out.voluntary_cancel_branch == "benign"
    else:
        # Punitive branch — sunk rewards included → CANCEL
        assert out.decision_kind == "CANCEL", (
            f"punitive branch should CANCEL but got {out.decision_kind} (ev={out.ev_hold_pendle})"
        )
        assert out.voluntary_cancel_branch == "punitive"


@pytest.mark.asyncio
async def test_default_branch_is_benign(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
) -> None:
    """DECIDE-02: BotConfig() defaults to voluntary_cancel_forfeits_accumulated=False (benign).

    Per P0-01 resolution 2026-04-23 — flag = False is the resolved default.
    [[Voluntary cancel reward behavior]]
    """
    db = seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    req = _build_eval_input()
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(
        req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None
    )
    assert out.voluntary_cancel_branch == "benign", (
        f"default branch must be benign, got {out.voluntary_cancel_branch!r}"
    )
