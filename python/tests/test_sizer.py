"""REWARD-03 / REWARD-04 sizer tests (Plan 03-03, Task 1).

Test IDs:
- T-03-S-01: $100 collateral → q_me_target == q_min (sub-cap fixed point)
- T-03-S-02: $5000 collateral → q_me_target < q_cap (cap-binding regime)
- T-03-S-03: InsufficientCollateralError (q_min > q_max)
- T-03-S-04: FillModelNoFreshFitError propagates (no fit row)
- T-03-S-05: LossModelNoFreshGridError propagates (no grid row)
- T-03-S-06: optimizer-dominates-q_min property test
- T-03-S-07: market_saturated shortcut (q_cap < q_min)

Helpers seed fill_model_fits + loss_grid_artifacts via direct INSERTs (test-only,
matching test_fill_model_predict_contract.py pattern). No new writer modules.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import (
    BotConfig,
    DataConfig,
    MarketCalibration,
)
from boros_brain.fill_model.predict import FillModelNoFreshFitError
from boros_brain.fill_model.schemas import FitArtifact
from boros_brain.loss_model.artifact import write_loss_grid_artifact
from boros_brain.loss_model.expected_loss import LossModelNoFreshGridError
from boros_brain.loss_model.schemas import LossGridArtifact, LossGridCell
from boros_brain.sizer.config import SizerConfig
from boros_brain.sizer.optimizer import q_me_target
from boros_brain.sizer.schemas import (
    InsufficientCollateralError,
    SizerInput,
    SizerOutput,
)
from boros_brain.state.writers.fill_model_fits import insert_fit_artifact

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = (
        ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    )
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def _make_config(
    *,
    sizer_config: SizerConfig | None = None,
) -> BotConfig:
    """Build a tiny BotConfig with optional sizer override."""
    kwargs = dict(
        mode="backtest",
        strategy_version="test",
        market_id=MARKET_ID,
        side="long",
        root_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        data=DataConfig(rpc_url_arbitrum="https://example.com"),
        markets=[
            MarketCalibration(
                market_id=MARKET_ID,
                scale=1.0,
                s=1.0,
                clo_lower_thresh=0.0,
                clo_upper_thresh=1.0,
                fIndex_oracle_address="0x0000000000000000000000000000000000000099",
                maturity_ts=1_700_000_000 + 365 * 86400,
            )
        ],
    )
    if sizer_config is not None:
        kwargs["sizer"] = sizer_config
    return BotConfig(**kwargs)


def _seed_fill_model_fit(
    db: Path, *, market_id: str = MARKET_ID, side: str = "long",
    fit_window_end_ts: int = 1_700_000_000,
) -> None:
    """Insert a known-good fill_model fit artifact (non-degraded, fresh)."""
    artifact = FitArtifact(
        run_id="seed-fit-001",
        fit_window_start_ts=fit_window_end_ts - 14 * 86400,
        fit_window_end_ts=fit_window_end_ts,
        market_id=market_id,
        side=side,  # type: ignore[arg-type]
        covariate_whitelist=[
            "basis_spread",
            "imbalance",
            "sin_settlement",
            "cos_settlement",
            "ewma_vol",
        ],
        beta=[-1.0, 0.5, -0.3, 0.1, 0.1, 0.2],  # intercept + 5 features
        beta_stderr=[0.1, 0.05, 0.05, 0.05, 0.05, 0.05],
        log_likelihood=-100.0,
        deviance=200.0,
        aic=220.0,
        n_observations=2000,
        converged=True,
        fit_status="ok",
        event_index_coverage="full",
        created_at=fit_window_end_ts,
    )
    insert_fit_artifact(db, artifact)


def _seed_loss_grid_artifact(
    db: Path,
    parquet_root: Path,
    *,
    market_id: str = MARKET_ID,
    side: str = "long",
    window_end_ts: int = 1_700_000_000,
) -> None:
    """Insert a known-good loss_grid artifact (full coverage, populated cells)."""
    cells = []
    for d_idx in range(7):
        for t_idx in range(6):
            cells.append(
                LossGridCell(
                    depth_bucket_idx=d_idx,
                    tau_bucket_idx=t_idx,
                    n_samples=10,
                    mean_pendle=-0.01 - 0.001 * d_idx,
                    std_pendle=0.002,
                    p5_pendle=-0.02 - 0.001 * d_idx,
                    p50_pendle=-0.01 - 0.001 * d_idx,
                    p95_pendle=-0.005 - 0.001 * d_idx,
                )
            )
    artifact = LossGridArtifact(
        run_id="seed-loss-001",
        market_id=market_id,
        side=side,  # type: ignore[arg-type]
        window_start_ts=window_end_ts - 90 * 86400,
        window_end_ts=window_end_ts,
        fit_status="ok",
        depth_bucket_edges=[0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 10000.0],
        tau_bucket_edges_days=[0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, 10000.0],
        cells=cells,
        event_index_coverage="full",
        created_at=0,
    )
    write_loss_grid_artifact(artifact, sqlite_path=db, parquet_root=parquet_root)


def _default_features() -> dict[str, float]:
    return {
        "basis_spread": 0.01,
        "imbalance": 0.0,
        "sin_settlement": 0.0,
        "cos_settlement": 1.0,
        "ewma_vol": 0.05,
    }


def _make_sizer_input(
    *,
    sigma_others_pendle: float = 60.0,
    e_liq_per_epoch_pendle: float = 273.0,
    side_split: float = 0.86,
    current_chain_ts: int = 1_700_000_060,
) -> SizerInput:
    return SizerInput(
        market_id=MARKET_ID,
        side="long",
        depth_from_mark_ticks=4,
        time_to_epoch_end_s=3600.0,
        time_to_maturity_s=20 * 86400,
        queue_ahead_wei=0,
        current_features=_default_features(),
        current_chain_ts=current_chain_ts,
        sigma_others_pendle=sigma_others_pendle,
        e_liq_per_epoch_pendle=e_liq_per_epoch_pendle,
        side_split=side_split,
        t_frac=1.0,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


def test_q_min_fixed_point_at_100_collateral(tmp_path: Path) -> None:
    """T-03-S-01 — At $100 collateral with notional_per_yu_usd=90000, Q_max ≈ Q_min,
    optimizer's degenerate-interval shortcut returns Q_me=Q_min trivially.

    Phase 3 ROADMAP Success Criterion #3 — sub-cap regime + collateral-constrained.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fill_model_fit(db)
    _seed_loss_grid_artifact(db, tmp_path / "parquet")

    config = _make_config(
        sizer_config=SizerConfig(
            collateral_usd=100.0,
            q_min_pendle=0.001,
            q_max_safety_margin=0.9,
            optimizer_grid_points=50,
            optimizer_method="grid_plus_scipy",
            notional_per_yu_usd=90_000.0,
        )
    )

    out = q_me_target(_make_sizer_input(), sqlite_path=db, config=config)
    assert isinstance(out, SizerOutput)
    # Q_max = 100 × 0.9 / 90000 = 0.001 = Q_min — degenerate-interval shortcut.
    assert out.q_me_target_pendle == pytest.approx(0.001, rel=1e-3)
    assert out.q_min_pendle == 0.001
    # Sub-cap regime expected (uncapped curve below cap_budget at this Q_me).
    assert out.regime == "sub_cap"
    # Intermediate values populated.
    assert 0.0 <= out.p_fill_at_target <= 1.0
    assert out.expected_loss_at_target < 0  # all loss-dominant cells
    assert out.r_capped_at_target > 0


def test_scale_up_to_5k_cap_binding(tmp_path: Path) -> None:
    """T-03-S-02 — At $5000 collateral with notional_per_yu_usd=1, Q_max = 4500
    PENDLE; Q_cap from REWARD-04 algebra is much smaller, so cap binds.

    Optimizer should return Q_me_target ≤ Q_cap; regime in {sub_cap, cap_binding,
    market_saturated} but not collateral-degenerate.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fill_model_fit(db)
    _seed_loss_grid_artifact(db, tmp_path / "parquet")

    config = _make_config(
        sizer_config=SizerConfig(
            collateral_usd=5000.0,
            q_min_pendle=0.001,
            q_max_safety_margin=0.9,
            optimizer_grid_points=50,
            optimizer_method="grid_plus_scipy",
            notional_per_yu_usd=1.0,
        )
    )

    out = q_me_target(_make_sizer_input(), sqlite_path=db, config=config)
    # Q_max = 5000 × 0.9 / 1 = 4500. Q_cap is finite at this scale (per
    # [[reward-cap-geometry-v05]]). upper = min(4500, q_cap).
    assert out.q_me_target_pendle > out.q_min_pendle
    # Q_me_target must be ≤ q_cap (or ≤ q_max if cap unreachable).
    upper_bound = min(out.q_max_pendle, out.q_cap_pendle)
    assert out.q_me_target_pendle <= upper_bound + 1e-9, (
        f"q_me_target={out.q_me_target_pendle} exceeded upper={upper_bound}"
    )
    # In cap-binding regime at this scale, the optimum is at or below Q_cap.
    assert out.q_me_target_pendle <= out.q_cap_pendle + 1e-9


def test_raises_insufficient_collateral(tmp_path: Path) -> None:
    """T-03-S-03 — q_min > q_max → InsufficientCollateralError raised."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fill_model_fit(db)
    _seed_loss_grid_artifact(db, tmp_path / "parquet")

    # collateral_usd=10 (min), notional_per_yu_usd=10000000 (max), q_min=1.0
    # → Q_max = 10 × 0.9 / 1e7 = 9e-7 < q_min=1.0. (using max-bounds for the
    # tightest pinch within validation bounds).
    config = _make_config(
        sizer_config=SizerConfig(
            collateral_usd=10.0,
            q_min_pendle=1.0,
            q_max_safety_margin=0.9,
            optimizer_grid_points=50,
            optimizer_method="grid_plus_scipy",
            notional_per_yu_usd=10_000_000.0,
        )
    )

    with pytest.raises(InsufficientCollateralError) as excinfo:
        q_me_target(_make_sizer_input(), sqlite_path=db, config=config)
    assert excinfo.value.q_min > excinfo.value.q_max


def test_propagates_fill_model_errors(tmp_path: Path) -> None:
    """T-03-S-04 — no fill_model fit row → FillModelNoFreshFitError propagates."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    # NB: skip _seed_fill_model_fit on purpose; seed loss grid so the error
    # surfacing is unambiguously from the fill model side.
    _seed_loss_grid_artifact(db, tmp_path / "parquet")

    config = _make_config()  # default sizer
    with pytest.raises(FillModelNoFreshFitError):
        q_me_target(_make_sizer_input(), sqlite_path=db, config=config)


def test_propagates_loss_model_errors(tmp_path: Path) -> None:
    """T-03-S-05 — no loss_grid row → LossModelNoFreshGridError propagates."""
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fill_model_fit(db)
    # NB: skip _seed_loss_grid_artifact on purpose.

    config = _make_config()
    with pytest.raises(LossModelNoFreshGridError):
        q_me_target(_make_sizer_input(), sqlite_path=db, config=config)


@pytest.mark.parametrize(
    "sigma_others",
    [10.0, 60.0, 200.0],
    ids=["thin", "anchor", "thick"],
)
def test_optimizer_dominates_q_min(tmp_path: Path, sigma_others: float) -> None:
    """T-03-S-06 — property test: optimizer is never WORSE than evaluate-at-Q_min.

    For multiple competition levels (sigma_others), assert the EV at the
    optimizer's chosen q_me_target is at least as good as the EV at q_min.
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fill_model_fit(db)
    _seed_loss_grid_artifact(db, tmp_path / "parquet")

    # Use a scaled-up collateral so the optimizer actually runs the grid
    # (not just the degenerate-interval shortcut).
    config = _make_config(
        sizer_config=SizerConfig(
            collateral_usd=5000.0,
            q_min_pendle=0.001,
            q_max_safety_margin=0.9,
            optimizer_grid_points=50,
            optimizer_method="grid_plus_scipy",
            notional_per_yu_usd=1.0,
        )
    )

    req = _make_sizer_input(sigma_others_pendle=sigma_others)
    out = q_me_target(req, sqlite_path=db, config=config)

    # Compute EV at q_min for the same inputs.
    from boros_brain.reward_model.r_capped import r_capped_curve
    from boros_brain.reward_model.schemas import RewardCurveInput

    r_at_qmin = r_capped_curve(
        RewardCurveInput(
            market_id=req.market_id,
            side=req.side,
            q_me_pendle=out.q_min_pendle,
            sigma_others_pendle=req.sigma_others_pendle,
            e_liq_per_epoch_pendle=req.e_liq_per_epoch_pendle,
            side_split=req.side_split,
            t_frac=req.t_frac,
            collateral_usd=config.sizer.collateral_usd,
            pendle_price_usd=config.pricing.pendle_price_usd,
            epoch_days=config.reward_share_model.epoch_days,
        )
    )
    ev_at_qmin = (
        r_at_qmin.r_capped_pendle
        - out.expected_loss_at_target * out.p_fill_at_target * out.q_min_pendle
    )

    # Optimizer ≥ q_min EV (within numerical slop).
    assert out.ev_at_target >= ev_at_qmin - 1e-9, (
        f"optimizer EV={out.ev_at_target} < EV-at-qmin={ev_at_qmin} "
        f"(sigma_others={sigma_others})"
    )


def test_market_saturated_shortcut(tmp_path: Path) -> None:
    """T-03-S-07 — q_cap < q_min → market_saturated regime, q_me_target = q_min.

    Forced by setting q_min very large relative to the algebraic q_cap given
    sigma_others / e_liq / collateral_usd configuration. (Concretely: at $100
    collateral with sigma_others=200 PENDLE and e_liq×side_split close to
    cap_budget, q_cap algebra returns a small or near-zero value.)
    """
    db = tmp_path / "state.sqlite"
    _apply_migrations(db)
    _seed_fill_model_fit(db)
    _seed_loss_grid_artifact(db, tmp_path / "parquet")

    # Push q_min above the algebraic q_cap. With $100 collateral, default
    # pendle_price_usd=7.0, epoch_days=7.0:
    #   cap_budget = 10 × 100 × (7/365) / 7.0 ≈ 2.74 PENDLE
    # With sigma_others=1000 and e_liq×side_split = cap_budget × 1.001, the
    # denominator (e_liq × side_split × t_frac − cap_budget × t_frac) is tiny,
    # making q_cap massive. To force q_cap < q_min, use a q_min above any
    # reasonable cap. The simplest construction: q_min=1.0 PENDLE (above the
    # full-bracket q_max) AND e_liq tiny so q_cap is tiny too.
    config = _make_config(
        sizer_config=SizerConfig(
            collateral_usd=100.0,
            q_min_pendle=1.0,        # very large floor
            q_max_safety_margin=0.9,
            optimizer_grid_points=50,
            optimizer_method="grid_plus_scipy",
            notional_per_yu_usd=10.0,  # Q_max = 9.0 PENDLE — generous
        )
    )

    # e_liq_per_epoch_pendle small → q_cap algebra returns small finite value
    # below q_min=1.0. (cap_budget=2.74; sigma=1000; e_liq×side_split=3 ⇒
    # q_cap = 1000×2.74 / (3 - 2.74) ≈ 10538 — too large. Different tactic:
    # set sigma_others=0.0001 + e_liq=3 + side_split=1 ⇒
    # q_cap = 0.0001×2.74 / (3-2.74) ≈ 1e-3 < q_min=1.0. ✓
    req = _make_sizer_input(
        sigma_others_pendle=0.0001,
        e_liq_per_epoch_pendle=3.0,
        side_split=1.0,
    )
    out = q_me_target(req, sqlite_path=db, config=config)
    assert out.regime == "market_saturated", (
        f"expected market_saturated; got regime={out.regime}, "
        f"q_cap={out.q_cap_pendle}, q_min={out.q_min_pendle}"
    )
    assert out.q_me_target_pendle == pytest.approx(out.q_min_pendle)
