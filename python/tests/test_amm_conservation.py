"""DATA-05 AMM conservation assertion tests.

Tests the assert_amm_conservation() check in order_book.py that ensures
total combined liquidity per snapshot >= total raw liquidity per snapshot.

Per-snapshot total invariant (not per-tick) — raw and combined are on
different tick grids (1bp vs tick_size), so the physical conservation
constraint is at the snapshot total level.

PITFALLS §B3: silently absorbing negative AMM share poisons every
fill-probability model downstream. This check fails loudly.

Cases:
1. test_amm_conservation_raises_on_violation
   Given a combined snapshot whose total < raw total,
   calling ingest_order_book_combined raises AMMConservationError.

2. test_amm_conservation_passes_on_valid
   Given a valid snapshot where combined >= raw on totals,
   ingest completes and writes parquet.

3. test_amm_conservation_subprocess_exit_nonzero
   Running ingest_order_book_combined via subprocess returns exit code != 0
   and stderr contains 'AMMConservationError' when given a violating combined
   snapshot.

4. test_amm_conservation_error_message_includes_offending_rows
   The AMMConservationError message includes at least one offending row
   in dict representation (for operator debuggability).

5. test_amm_conservation_cli_subprocess_exit_nonzero
   Running the CLI (python -m boros_brain.data.ingester.cli --kind
   order_book_combined --raw-src ...) with a violating fixture exits non-zero
   and prints AMMConservationError to stderr. This validates the full
   bulk-ingest path: the shell script passes --raw-src, the CLI forwards it
   to ingest_order_book_combined, and the gate fires before the parquet write.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_YAML = REPO_ROOT / "strategy" / "v0.5-default.yaml"
PYTHON_DIR = REPO_ROOT / "python"

# Violating combined: total combined per snapshot < total raw per snapshot
VIOLATING_RAW = FIXTURES / "amm_conservation_violating_snapshot.ndjson"
VIOLATING_COMBINED = FIXTURES / "amm_conservation_violating_combined.ndjson"

VALID_RAW = FIXTURES / "amm_conservation_valid_snapshot.ndjson"
VALID_COMBINED = FIXTURES / "amm_conservation_valid_combined.ndjson"


def test_amm_conservation_raises_on_violation(tmp_path: Path) -> None:
    """Given a combined snapshot with total < raw total,
    ingest_order_book_combined must raise AMMConservationError."""
    from boros_brain.data.ingester.exceptions import AMMConservationError
    from boros_brain.data.ingester.order_book import ingest_order_book_combined

    with pytest.raises(AMMConservationError) as exc_info:
        ingest_order_book_combined(
            VIOLATING_COMBINED,
            VIOLATING_RAW,
            market_id="ETH",
            tick_size="0.01",
            out_root=tmp_path,
        )
    assert "AMM conservation violated" in str(exc_info.value)


def test_amm_conservation_passes_on_valid(tmp_path: Path) -> None:
    """Given a valid snapshot where combined >= raw on snapshot totals,
    ingest completes and writes parquet."""
    from boros_brain.data.ingester.order_book import ingest_order_book_combined

    result = ingest_order_book_combined(
        VALID_COMBINED,
        VALID_RAW,
        market_id="ETH",
        tick_size="0.01",
        out_root=tmp_path,
    )
    # 1 hourly snapshot in the valid fixture, exploded to 4 tick rows (2 long + 2 short)
    assert result.rows_written == 4
    part_dir = tmp_path / "order_book_combined" / "market_id=ETH"
    assert part_dir.exists()


def test_amm_conservation_subprocess_exit_nonzero(tmp_path: Path) -> None:
    """Subprocess ingest with a violating combined snapshot must return non-zero
    exit code and stderr must contain 'AMMConservationError'."""
    # Use Python -c to call the function directly, raising on violation
    script = (
        "from pathlib import Path; "
        "from boros_brain.data.ingester.order_book import ingest_order_book_combined; "
        f"ingest_order_book_combined(Path('{VIOLATING_COMBINED}'), Path('{VIOLATING_RAW}'), "
        f"market_id='ETH', tick_size='0.01', out_root=Path('{tmp_path}'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, f"Expected non-zero exit. stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "AMMConservationError" in result.stderr, f"Expected 'AMMConservationError' in stderr. Got: {result.stderr!r}"


def test_amm_conservation_error_message_includes_offending_rows(tmp_path: Path) -> None:
    """AMMConservationError message must include the first offending rows as dicts,
    for operator debuggability (per research Pattern 9 snippet)."""
    from boros_brain.data.ingester.exceptions import AMMConservationError
    from boros_brain.data.ingester.order_book import ingest_order_book_combined

    with pytest.raises(AMMConservationError) as exc_info:
        ingest_order_book_combined(
            VIOLATING_COMBINED,
            VIOLATING_RAW,
            market_id="ETH",
            tick_size="0.01",
            out_root=tmp_path,
        )
    msg = str(exc_info.value)
    # The message should include snapshot info (snapshot_ts is the partition key)
    assert "snapshot" in msg.lower(), f"Error message should reference the offending snapshot. Got: {msg!r}"
    # Should contain dict-like content (either '{' or 'first 5')
    assert (
        "{" in msg or "first" in msg
    ), f"Error message should include dict representation of offending rows. Got: {msg!r}"


def test_amm_conservation_cli_subprocess_exit_nonzero(tmp_path: Path) -> None:
    """Full CLI path: --kind order_book_combined --raw-src <violating> exits non-zero
    and prints AMMConservationError to stderr.

    This is the end-to-end validation of the bulk-ingest wiring:
      scripts/05_1_bulk_ingest.sh derives raw_src and passes --raw-src to the CLI,
      the CLI forwards it to ingest_order_book_combined, and the DATA-05 gate
      raises AMMConservationError before any parquet write (PITFALLS §B3).
    """
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    out_dir = tmp_path / "parquet"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "boros_brain.data.ingester.cli",
            "--kind",
            "order_book_combined",
            "--src",
            str(VIOLATING_COMBINED),
            "--raw-src",
            str(VIOLATING_RAW),
            "--market-id",
            "ETH",
            "--tick-size",
            "0.01",
            "--out",
            str(out_dir),
            "--config",
            str(STRATEGY_YAML),
        ],
        capture_output=True,
        text=True,
        cwd=str(PYTHON_DIR),
        env={
            **__import__("os").environ,
            "BOROS_LOGS_DIR": str(logs_dir),
        },
    )
    assert completed.returncode != 0, (
        f"Expected non-zero exit from CLI with violating fixture. "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )
    assert (
        "AMMConservationError" in completed.stderr
    ), f"Expected 'AMMConservationError' in CLI stderr. Got: {completed.stderr!r}"
    # No parquet should have been written (gate fires before write)
    parquet_files = list(out_dir.rglob("*.parquet")) if out_dir.exists() else []
    assert (
        not parquet_files
    ), f"Parquet files written despite AMMConservationError (gate did not fire before write): {parquet_files}"
