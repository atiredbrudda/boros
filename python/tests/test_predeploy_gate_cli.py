"""A5 absorbed — predeploy_gate CLI tests (RED until 04-06 lands).

Covers:
  - test_gate_passes_on_clean_run: shortlist contains market → exit 0, row with gate_passed=True
  - test_gate_fails_when_market_dropped: shortlist missing market → exit 1, gate_passed=False
  - test_gate_records_git_sha_and_config_hash: Pitfall #8 — provenance of each gate run
    (git_sha and config_hash must be non-empty strings in the predeploy_gate_records row)

A5 = Pre-deploy gate: before going live, the screener must confirm the target market
is still in the shortlist. If it has been screened out since last calibration,
the bot must not place any orders.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: predeploy_gate module lands in Plan 04-06.
predeploy_mod = pytest.importorskip("boros_brain.decision.predeploy_gate")
run_predeploy_gate = predeploy_mod.run_predeploy_gate

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_gate_passes_on_clean_run(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """A5: screener returns shortlist containing the config market → gate passes (exit 0).

    Asserts one row in predeploy_gate_records with gate_passed=True.
    """
    from tests.conftest import apply_migrations

    apply_migrations(tmp_sqlite_path)

    with patch(
        "boros_brain.screener.economics_gate.run_screener",
        return_value=[MARKET_ID],  # shortlist includes our market
    ):
        exit_code = run_predeploy_gate(
            default_config, sqlite_path=tmp_sqlite_path, run_id="test-gate-001"
        )

    assert exit_code == 0, f"Expected exit code 0 (gate passes), got {exit_code}"

    # Verify the record was written.
    from boros_brain.state.db import open_connection

    with open_connection(tmp_sqlite_path) as conn:
        rows = conn.execute(
            "SELECT gate_passed FROM predeploy_gate_records WHERE run_id = 'test-gate-001'"
        ).fetchall()
    assert len(rows) == 1, f"Expected 1 predeploy_gate_records row, got {len(rows)}"
    assert rows[0][0] == 1, f"Expected gate_passed=True (1), got {rows[0][0]}"


@pytest.mark.asyncio
async def test_gate_fails_when_market_dropped(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """A5: screener returns shortlist NOT containing config market → exit 1, gate_passed=False.

    The operator is alerted that the market has been screened out.
    """
    from tests.conftest import apply_migrations

    apply_migrations(tmp_sqlite_path)

    with patch(
        "boros_brain.screener.economics_gate.run_screener",
        return_value=["BINANCE-BTCUSDT-26DEC2025"],  # different market — ours not included
    ):
        exit_code = run_predeploy_gate(
            default_config, sqlite_path=tmp_sqlite_path, run_id="test-gate-002"
        )

    assert exit_code == 1, f"Expected exit code 1 (gate fails), got {exit_code}"

    from boros_brain.state.db import open_connection

    with open_connection(tmp_sqlite_path) as conn:
        rows = conn.execute(
            "SELECT gate_passed FROM predeploy_gate_records WHERE run_id = 'test-gate-002'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0, f"Expected gate_passed=False (0), got {rows[0][0]}"


@pytest.mark.asyncio
async def test_gate_records_git_sha_and_config_hash(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """A5 Pitfall #8: every gate run records git_sha and config_hash for full provenance.

    A pre-deploy gate record without provenance is unauditable — you cannot tell
    which code version or which config was used for the gate decision.
    """
    from tests.conftest import apply_migrations

    apply_migrations(tmp_sqlite_path)

    with patch(
        "boros_brain.screener.economics_gate.run_screener",
        return_value=[MARKET_ID],
    ):
        run_predeploy_gate(
            default_config, sqlite_path=tmp_sqlite_path, run_id="test-gate-003"
        )

    from boros_brain.state.db import open_connection

    with open_connection(tmp_sqlite_path) as conn:
        rows = conn.execute(
            "SELECT git_sha, config_hash FROM predeploy_gate_records WHERE run_id = 'test-gate-003'"
        ).fetchall()
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
    git_sha, config_hash = rows[0]
    assert isinstance(git_sha, str) and len(git_sha) >= 7, (
        f"git_sha must be a non-empty string (>=7 chars), got {git_sha!r}"
    )
    assert isinstance(config_hash, str) and len(config_hash) > 0, (
        f"config_hash must be a non-empty string, got {config_hash!r}"
    )
