"""BACK-06 — voluntary cancel forfeit sensitivity sweep.

Test functions:
  - test_two_branches_produced: sweep emits two rows (branch=benign, branch=punitive)
  - test_divergence_under_threshold_logs_sanity_pass: divergence < warn_pct → no follow-up flag
  - test_divergence_over_threshold_emits_followup_flag: divergence >= 10% → forfeit_branch_load_bearing flag

Turns GREEN in Plan 05-06 when boros_brain.backtest.sweeps.forfeit_branch lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-06.
forfeit_mod = pytest.importorskip("boros_brain.backtest.sweeps.forfeit_branch")
run_forfeit_branch_sweep = forfeit_mod.run_forfeit_branch_sweep

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_two_branches_produced(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-06: forfeit branch sweep emits exactly two rows: branch=benign and branch=punitive."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-06 implements this — currently RED")


def test_divergence_under_threshold_logs_sanity_pass(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-06: divergence < voluntary_cancel_divergence_warn_pct → no forfeit_branch_load_bearing flag."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-06 implements this — currently RED")


def test_divergence_over_threshold_emits_followup_flag(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-06: divergence >= 10% (voluntary_cancel_divergence_warn_pct) → forfeit_branch_load_bearing flag set."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-06 implements this — currently RED")
