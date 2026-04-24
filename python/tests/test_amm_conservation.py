"""DATA-05 AMM conservation assertion tests.

Tests the assert_amm_conservation() check in order_book.py that ensures
combined_size(delta) >= raw_book_size(delta) for every tick in a snapshot.

PITFALLS §B3: silently absorbing negative AMM share poisons every
fill-probability model downstream. This check fails loudly.

Cases:
1. test_amm_conservation_raises_on_violation
   Given a combined snapshot where tick=100 has combined_size < raw_size,
   calling ingest_order_book_combined raises AMMConservationError.

2. test_amm_conservation_passes_on_valid
   Given a valid snapshot where combined >= raw on all ticks,
   ingest completes and writes parquet.

3. test_amm_conservation_subprocess_exit_nonzero
   Running ingest_order_book_combined via subprocess returns exit code != 0
   and stderr contains 'AMMConservationError' when given a violating combined
   snapshot.

4. test_amm_conservation_error_message_includes_offending_rows
   The AMMConservationError message includes at least one offending row
   in dict representation (for operator debuggability).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Raw snapshot: tick=100 has sz=1e18 (large) — violating combined has sz_combined=0.5e18
VIOLATING_RAW = FIXTURES / "amm_conservation_violating_snapshot.ndjson"
VIOLATING_COMBINED = FIXTURES / "amm_conservation_violating_combined.ndjson"

VALID_RAW = FIXTURES / "amm_conservation_valid_snapshot.ndjson"
VALID_COMBINED = FIXTURES / "amm_conservation_valid_combined.ndjson"


def test_amm_conservation_raises_on_violation(tmp_path: Path) -> None:
    """Given a combined snapshot with combined_size < raw_size on tick=100,
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
    """Given a valid snapshot where combined >= raw on all ticks,
    ingest completes and writes parquet."""
    from boros_brain.data.ingester.order_book import ingest_order_book_combined

    result = ingest_order_book_combined(
        VALID_COMBINED,
        VALID_RAW,
        market_id="ETH",
        tick_size="0.01",
        out_root=tmp_path,
    )
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
    # The message should include tick info (100 is the violating tick)
    assert "tick" in msg.lower() or "100" in msg, f"Error message should reference the offending tick. Got: {msg!r}"
    # Should contain dict-like content (either '{' or 'first 5')
    assert (
        "{" in msg or "first" in msg
    ), f"Error message should include dict representation of offending rows. Got: {msg!r}"
