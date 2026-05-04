"""Phase 05.4-01 Bug A smoke tests: calibration migration + history loader.

Regression suite proving that:
  1. Alembic migration 0008 applies cleanly to a fresh SQLite and brings
     ``effective_at_utc`` + ``next_refresh_at_utc`` columns live.
  2. Two operator rows (prior + current epoch) load via
     ``_load_operator_calibration_history`` in effective_at_utc-ASC order.
  3. ``_calibration_at_chain_ts`` returns a non-None operator row for any
     chain_ts within the replay window — no ``no_operator_calibration`` warning.

Background: Phase 05.3 T6 dry-run (run_id 01KQFABR9VNPMKKQYPTQGRJMDR) emitted
~4.5M ``no_operator_calibration`` warnings because Alembic 0008 was never applied
to state/state.sqlite, causing ``_load_operator_calibration_history`` to query a
column that didn't exist. Engine fell through to default fallback (e_liq=100,
side_split=0.5) for every tick.

These tests are GREEN after applying the migration and inserting rows via
``scripts/insert_operator_calibration_rows_phase054.py``. They serve as a
regression guard: future plan runs that drop rows or downgrade alembic will
be caught here before reaching Plan 04's binding re-run.

[[phase-05-4-bug-a-calibration-migration]]
[[phase-05-3-bugs-discovered-during-t6]]
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.state.writers.market_reward_calibration import (
    insert_market_reward_calibration,
)

# CONTEXT.md-locked values (do NOT change — these are the values inserted into
# the live state DB and consumed by Plan 04's binding re-run)
MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"
PRIOR_EFFECTIVE_AT = "2026-03-15T00:00:00+00:00"
CURRENT_EFFECTIVE_AT = "2026-04-23T00:00:00+00:00"
PRIOR_LONG_SPLIT = 0.327
CURRENT_LONG_SPLIT = 0.760
E_LIQ = 309.96


def _to_unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).timestamp())


def _apply_migrations(db: Path) -> None:
    """Apply alembic head to a fresh DB. Canonical migration helper."""
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_DIR = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations"
    cfg = Config(str(ALEMBIC_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def _seed_two_epoch_rows(sqlite_path: Path) -> None:
    """Insert prior- and current-epoch calibration rows for the binding market.

    Values from CONTEXT.md lines 95-97 (Phase 05.4-01 locked values).
    Insertion order is reversed vs effective_at_utc order to ensure the loader
    sorts by effective_at_utc, not insertion order (same anti-regression pattern
    as test_calibration_chain_ts_aware.py::_seed_two_epoch_rows).
    """
    # Insert current first so a calibrated_at-DESC reader would pick this one first.
    insert_market_reward_calibration(
        sqlite_path,
        market_id=MARKET_ID,
        e_liq_per_epoch_pendle=E_LIQ,
        long_side_split=CURRENT_LONG_SPLIT,
        short_side_split=1.0 - CURRENT_LONG_SPLIT,
        calibrated_at_utc="2026-04-30T08:30:30+00:00",
        effective_at_utc=CURRENT_EFFECTIVE_AT,
        next_refresh_at_utc="2026-05-02T00:00:00+00:00",
        source="dapp_ui",
        run_id="phase054-smoke-current",
    )
    # Prior inserted after — effective_at_utc is earlier, so a correct reader
    # must ORDER BY effective_at_utc ASC to yield prior before current.
    insert_market_reward_calibration(
        sqlite_path,
        market_id=MARKET_ID,
        e_liq_per_epoch_pendle=E_LIQ,
        long_side_split=PRIOR_LONG_SPLIT,
        short_side_split=1.0 - PRIOR_LONG_SPLIT,
        calibrated_at_utc="2026-04-30T08:30:26+00:00",
        effective_at_utc=PRIOR_EFFECTIVE_AT,
        next_refresh_at_utc="2026-04-23T00:00:00+00:00",
        source="dapp_ui",
        run_id="phase054-smoke-prior",
    )


def _build_engine(
    sqlite_path: Path,
    parquet_root: Path,
    default_config: BotConfig,
) -> ReplayEngine:
    return ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-phase054-smoke",
        manifest=None,
    )


# ── Test 1: Migration 0008 brings effective_at_utc column live ──────────────


def test_migration_0008_brings_effective_at_utc_column_live(tmp_path: Path) -> None:
    """Alembic head=0008 must add effective_at_utc + next_refresh_at_utc columns
    to market_reward_calibration in a fresh DB.

    This is the minimal proof that Bug A's root cause is fixed: before this
    migration, the column did not exist and _load_operator_calibration_history
    raised an OperationalError on every query.
    """
    db = tmp_path / "smoke.sqlite"
    _apply_migrations(db)

    conn = sqlite3.connect(str(db))
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(market_reward_calibration)").fetchall()]
    finally:
        conn.close()

    assert "effective_at_utc" in cols, f"effective_at_utc column missing after migration 0008; got cols={cols}"
    assert "next_refresh_at_utc" in cols, f"next_refresh_at_utc column missing after migration 0008; got cols={cols}"


# ── Test 2: Two rows load via the canonical history loader in ASC order ──────


def test_two_operator_rows_load_into_calibration_history(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet: Callable[..., Any],
) -> None:
    """_load_operator_calibration_history must return >=2 rows in
    effective_at_utc-ASC order with the CONTEXT.md-locked split values.

    This proves:
    a) The column exists (migration applied), so the query succeeds.
    b) The loader sorts by effective_at_utc ASC (not calibrated_at_utc,
       not insertion order — Bug #6 anti-regression).
    c) side_split values match the locked prior=0.327, current=0.760.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    db = tmp_path / "smoke.sqlite"
    _apply_migrations(db)
    _seed_two_epoch_rows(db)

    engine = _build_engine(db, parquet_root, default_config)
    history = engine._load_operator_calibration_history()

    assert len(history) >= 2, (
        f"expected >=2 operator rows from _load_operator_calibration_history, " f"got {len(history)}: {history}"
    )

    # The loader returns side_split (not long_side_split) — for side='long',
    # side_split == long_side_split.
    splits = [row["side_split"] for row in history]

    # effective_at_utc ASC ordering: prior (0.327) must come before current (0.760)
    assert splits[0] == pytest.approx(
        PRIOR_LONG_SPLIT
    ), f"first row (prior epoch) must have side_split={PRIOR_LONG_SPLIT}, got {splits[0]}"
    assert splits[1] == pytest.approx(
        CURRENT_LONG_SPLIT
    ), f"second row (current epoch) must have side_split={CURRENT_LONG_SPLIT}, got {splits[1]}"

    # Verify effective_at_utc values are strictly ascending
    eff_ats = [row["effective_at_utc"] for row in history]
    prior_eff = eff_ats[0]
    current_eff = eff_ats[1]
    assert prior_eff < current_eff, f"effective_at_utc must be strictly ascending: {prior_eff} < {current_eff} failed"


# ── Test 3: _calibration_at_chain_ts returns operator row (not None/fallback) ─


def test_calibration_at_chain_ts_returns_operator_row(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet: Callable[..., Any],
) -> None:
    """_calibration_at_chain_ts must return a non-None operator row for any
    chain_ts within the replay window (after rows are seeded).

    If it returns None or the fallback dict (data_source='default_fallback'),
    the 'no_operator_calibration' warning fires in the engine and the reward
    leg is calculated with wrong defaults — the exact Bug A failure mode.

    chain_ts=2026-04-25 is well within the current epoch
    (effective_at_utc=2026-04-23), so this should resolve to the current row.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    db = tmp_path / "smoke.sqlite"
    _apply_migrations(db)
    _seed_two_epoch_rows(db)

    engine = _build_engine(db, parquet_root, default_config)
    # Pre-load history (simulates engine startup)
    engine._calibration_history = engine._load_operator_calibration_history()

    # chain_ts well within the current epoch (2026-04-23 boundary + 2 days)
    chain_ts = _to_unix("2026-04-25T12:00:00+00:00")
    row = engine._calibration_at_chain_ts(chain_ts)

    assert row is not None, (
        "expected operator row for chain_ts=2026-04-25, got None "
        "(no_operator_calibration would fire — Bug A regression)"
    )
    assert row.get("source") != "default_fallback", (
        f"expected operator row, got fallback dict: {row} " "(no_operator_calibration would fire — Bug A regression)"
    )
    assert row["side_split"] == pytest.approx(CURRENT_LONG_SPLIT), (
        f"chain_ts=2026-04-25 (current epoch) must resolve to "
        f"side_split={CURRENT_LONG_SPLIT}, got {row['side_split']}"
    )
    assert row["e_liq_per_epoch_pendle"] == pytest.approx(
        E_LIQ
    ), f"e_liq_per_epoch_pendle must be {E_LIQ}, got {row['e_liq_per_epoch_pendle']}"
