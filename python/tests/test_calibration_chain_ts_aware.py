"""Phase 05.2 Bug #6: replay calibration must be effective_at_utc-keyed and chain_ts-aware.

Prior to fix: ``_read_operator_calibration_sql`` ordered by ``calibrated_at_utc DESC LIMIT 1``
and was called once at startup. The same row was applied to every tick. In the binding
ship-gate run ``01KQEZ6M0SWVXX3H4G5W7RNFS8`` this caused the engine to retroactively apply
the current-epoch ``long_side_split`` (0.760) to historical ticks from the prior epoch
(where the real-world split was 0.327). Inflated the verdict by 0.760 / 0.327 = 2.32x.

The fix:

1. Load all operator rows for the market at startup, sorted by ``effective_at_utc`` ASC.
2. Per-tick lookup: pick the row with the largest ``effective_at_utc`` that is
   ``<= chain_ts``. Fall back to the earliest row (with a warning) if ``chain_ts``
   predates all rows.

[[ship-gate-bug-6-epoch-keyed-calibration]]
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.state.writers.market_reward_calibration import (
    insert_market_reward_calibration,
)

MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"

PRIOR_EPOCH_EFFECTIVE_AT = "2026-04-18T00:00:00+00:00"
CURRENT_EPOCH_EFFECTIVE_AT = "2026-04-25T00:00:00+00:00"

PRIOR_LONG_SPLIT = 0.327
CURRENT_LONG_SPLIT = 0.760


def _to_unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).timestamp())


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_DIR = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations"
    cfg = Config(str(ALEMBIC_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def _seed_two_epoch_rows(sqlite_path: Path) -> None:
    """Insert prior- and current-epoch rows for the binding market.

    Note: ``calibrated_at_utc`` (when the row was inserted) is set to a value
    that *contradicts* the epoch ordering — the prior-epoch row is "calibrated"
    AFTER the current-epoch row. This ensures a chain_ts-aware reader cannot
    accidentally pass by ordering by ``calibrated_at_utc`` (Bug #6's exact
    failure mode).
    """
    insert_market_reward_calibration(
        sqlite_path,
        market_id=MARKET_ID,
        e_liq_per_epoch_pendle=309.96,
        long_side_split=CURRENT_LONG_SPLIT,
        short_side_split=1.0 - CURRENT_LONG_SPLIT,
        calibrated_at_utc="2026-04-30T08:30:26+00:00",
        effective_at_utc=CURRENT_EPOCH_EFFECTIVE_AT,
        next_refresh_at_utc="2026-05-02T00:00:00+00:00",
        source="dapp_ui",
        run_id="test-bug6-current",
    )
    # Prior-epoch row inserted AFTER the current-epoch row — a calibrated_at-DESC
    # reader would still pick this one (latest insert), masking the regression.
    insert_market_reward_calibration(
        sqlite_path,
        market_id=MARKET_ID,
        e_liq_per_epoch_pendle=309.96,
        long_side_split=PRIOR_LONG_SPLIT,
        short_side_split=1.0 - PRIOR_LONG_SPLIT,
        calibrated_at_utc="2026-04-30T08:30:30+00:00",
        effective_at_utc=PRIOR_EPOCH_EFFECTIVE_AT,
        next_refresh_at_utc="2026-04-25T00:00:00+00:00",
        source="dapp_ui",
        run_id="test-bug6-prior",
    )


def _build_engine(sqlite_path: Path, parquet_root: Path, default_config: BotConfig) -> ReplayEngine:
    return ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-bug6",
        manifest=None,
    )


def test_chain_ts_inside_prior_epoch_picks_prior_split(
    tmp_path: Path, default_config: BotConfig, seed_market_trades_parquet
) -> None:
    """A chain_ts that falls INSIDE the prior epoch's effective window must
    resolve to the prior-epoch row (long_split=0.327), not the current-epoch row.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = tmp_path / "test_state.sqlite"
    _apply_migrations(sqlite_path)
    _seed_two_epoch_rows(sqlite_path)

    engine = _build_engine(sqlite_path, parquet_root, default_config)

    chain_ts = _to_unix("2026-04-22T00:00:00+00:00")  # midway through prior epoch
    calib = engine._calibration_at_chain_ts(chain_ts)

    assert calib["side_split"] == pytest.approx(PRIOR_LONG_SPLIT), (
        f"chain_ts {chain_ts} (prior epoch) must resolve to prior-epoch row "
        f"(long_split={PRIOR_LONG_SPLIT}), got {calib['side_split']}. "
        "Reader is not effective_at_utc-keyed."
    )


def test_chain_ts_inside_current_epoch_picks_current_split(
    tmp_path: Path, default_config: BotConfig, seed_market_trades_parquet
) -> None:
    """A chain_ts that falls inside the current epoch resolves to the current-epoch row."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = tmp_path / "test_state.sqlite"
    _apply_migrations(sqlite_path)
    _seed_two_epoch_rows(sqlite_path)

    engine = _build_engine(sqlite_path, parquet_root, default_config)

    chain_ts = _to_unix("2026-04-29T00:00:00+00:00")  # inside current epoch
    calib = engine._calibration_at_chain_ts(chain_ts)

    assert calib["side_split"] == pytest.approx(CURRENT_LONG_SPLIT), (
        f"chain_ts {chain_ts} (current epoch) must resolve to current-epoch row "
        f"(long_split={CURRENT_LONG_SPLIT}), got {calib['side_split']}."
    )


def test_chain_ts_before_all_rows_falls_back_to_earliest(
    tmp_path: Path, default_config: BotConfig, seed_market_trades_parquet, capsys
) -> None:
    """When chain_ts predates the earliest effective_at_utc, fall back to the earliest
    row and emit a structured warning. Same fallback shape as the sigma_others
    earliest-snapshot fallback added in W5-A.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = tmp_path / "test_state.sqlite"
    _apply_migrations(sqlite_path)
    _seed_two_epoch_rows(sqlite_path)

    engine = _build_engine(sqlite_path, parquet_root, default_config)

    chain_ts = _to_unix("2026-04-10T00:00:00+00:00")  # before both rows
    calib = engine._calibration_at_chain_ts(chain_ts)

    assert calib["side_split"] == pytest.approx(PRIOR_LONG_SPLIT), (
        "chain_ts before all rows must fall back to the earliest row, " f"got {calib['side_split']}."
    )
    out = capsys.readouterr().out
    assert (
        "calibration_pre_history_fallback" in out or "earliest" in out.lower()
    ), f"Expected a warning log when falling back; got stdout: {out!r}"


def test_evaluate_input_uses_chain_ts_aware_calibration(
    tmp_path: Path, default_config: BotConfig, seed_market_trades_parquet
) -> None:
    """Integration: ``_build_evaluate_input`` must propagate the chain_ts-aware split,
    not a static one read at startup. This is the load-bearing assertion — Bug #6
    was specifically that the static read was used per-tick.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    sqlite_path = tmp_path / "test_state.sqlite"
    _apply_migrations(sqlite_path)
    _seed_two_epoch_rows(sqlite_path)

    engine = _build_engine(sqlite_path, parquet_root, default_config)

    from boros_brain.backtest.synthetic_orders import SyntheticOrder

    order = SyntheticOrder(
        order_id="test_order",
        market_id=MARKET_ID,
        side="long",
        tick=9400,
        q_me_pendle=4.92,
        placed_at_ts=_to_unix("2026-04-20T00:00:00+00:00"),
        depth_from_mark_ticks=10,
        queue_ahead_wei=10**18,
    )

    prior_ts = _to_unix("2026-04-22T00:00:00+00:00")
    current_ts = _to_unix("2026-04-29T00:00:00+00:00")

    # The reader returns the per-tick row; the *static* startup calib (passed to
    # _build_evaluate_input) is intentionally inconsistent — the chain_ts-aware
    # path must override it.
    static_calib = {
        "e_liq_per_epoch_pendle": 999.99,
        "side_split": 0.999,  # bogus — must not appear in the EvaluateInput
        "sigma_others_pendle": 0.0,
        "calibrated_at_utc": "1970-01-01T00:00:00+00:00",
        "source": "test_static_must_be_ignored",
    }

    eval_in_prior = engine._build_evaluate_input(order, static_calib, prior_ts)
    assert eval_in_prior.side_split == pytest.approx(PRIOR_LONG_SPLIT)
    assert eval_in_prior.e_liq_per_epoch_pendle == pytest.approx(309.96)

    eval_in_current = engine._build_evaluate_input(order, static_calib, current_ts)
    assert eval_in_current.side_split == pytest.approx(CURRENT_LONG_SPLIT)
