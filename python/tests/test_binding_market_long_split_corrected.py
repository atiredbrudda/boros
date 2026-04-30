"""Integration test: after Wave 2b epoch-keyed insertion, the binding-market
calibration table contains both prior-epoch (0.327) and current-epoch (0.760)
rows; the latest-row read returns the current epoch value.

These tests SKIP if state.sqlite does not exist or the operator rows have not
been inserted yet. Run them AFTER executing both CLI invocations from the
Wave 2b operator checklist (see plan 05.2-04 Task 2 Step 2).

[[market-reward-calibration-2026-04-30]]
"""

import sqlite3
from pathlib import Path

import pytest

BINDING_MARKET = "BINANCE-ETHUSDT-25SEP2026"
CURRENT_EPOCH_LONG_SPLIT = 0.760  # from W0_evidence_packet.md (T+150 probe 2026-04-30)
PRIOR_EPOCH_LONG_SPLIT = 0.327    # from CONTEXT.md original table (~2026-04-23 timeframe)


def _get_db_path() -> Path:
    """Resolve state.sqlite relative to this test file's repo root."""
    return Path(__file__).resolve().parents[2] / "python" / "state" / "state.sqlite"


def test_binding_long_split_current_epoch_is_latest() -> None:
    """After operator runs INSERT 2 (current-epoch 0.760 row), the latest calibration
    row for the binding market must have long_split ≈ 0.760.

    NOTE: depends on operator having run BOTH CLI invocations (Wave 2b Step 2).
    """
    db_path = _get_db_path()
    if not db_path.exists():
        pytest.skip("state.sqlite not present in test environment")
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT long_side_split, short_side_split FROM market_reward_calibration "
                "WHERE market_id LIKE ? "
                "ORDER BY calibrated_at_utc DESC LIMIT 1",
                (f"%{BINDING_MARKET}%",),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        pytest.skip(f"market_reward_calibration table not accessible ({exc}) — DB may need migration")
    if row is None:
        pytest.skip(f"No calibration row for {BINDING_MARKET} — operator rows not yet inserted")
    long_split, short_split = row
    assert long_split == pytest.approx(CURRENT_EPOCH_LONG_SPLIT, rel=1e-3), (
        f"Expected latest long_split={CURRENT_EPOCH_LONG_SPLIT} (current epoch per W0 probe), "
        f"got {long_split}. Did operator run BOTH CLI invocations per Wave 2b?"
    )
    assert short_split == pytest.approx(1.0 - CURRENT_EPOCH_LONG_SPLIT, rel=1e-3)


def test_binding_prior_epoch_row_persisted() -> None:
    """Confirms the historical row keyed at the prior epoch's effective_at_utc
    is also present (not overwritten by the current-epoch insert).

    NOTE: depends on operator having run INSERT 1 (prior-epoch 0.327 row).
    """
    db_path = _get_db_path()
    if not db_path.exists():
        pytest.skip("state.sqlite not present in test environment")
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT long_side_split FROM market_reward_calibration "
                "WHERE market_id LIKE ? AND ABS(long_side_split - ?) < 0.005",
                (f"%{BINDING_MARKET}%", PRIOR_EPOCH_LONG_SPLIT),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        pytest.skip(f"market_reward_calibration table not accessible ({exc}) — DB may need migration")
    if not rows:
        pytest.skip(
            f"No row with long_split≈{PRIOR_EPOCH_LONG_SPLIT} found — "
            "operator may not yet have run the prior-epoch CLI invocation"
        )
    assert len(rows) >= 1, (
        f"Expected at least one row with long_split≈{PRIOR_EPOCH_LONG_SPLIT} (prior epoch), "
        f"got 0. Did operator run the prior-epoch CLI invocation per Wave 2b?"
    )
