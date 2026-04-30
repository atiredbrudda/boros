"""Backtest-specific exceptions.

Bug #3 fix (Phase 05.2 Wave 3): the original `replay.py:489-500` used a bare
`except Exception: pass` that silently set sigma_others=0 when competition_history
was empty. This caused infinite reward share (0 denominator) and ~330,000× APR
inflation.

This module defines `EmptyCompetitionPoolError`, raised whenever the backtest
parquet read for sigma_others cannot find valid order-book data. No silent zero
default is allowed — empty pool is a real engine failure.

[[backtest-sigma-others-parquet-read-2026-04-30]]
"""

from __future__ import annotations


class EmptyCompetitionPoolError(RuntimeError):
    """Raised when order_book_raw parquet yields no rows for sigma_others computation.

    Bug #3 (Phase 05.2 Wave 3): replaces the bare-except sigma_others=0 path at
    replay.py:489-500 with a loud, inspectable failure. Empty parquet is a data
    problem — not a numerical edge case — and must surface as such.

    Attributes
    ----------
    market_id:
        The market for which parquet data was sought.
    chain_ts:
        The chain timestamp (int) at which the read was attempted.
    reason:
        Human-readable description of why the pool is considered empty.

    [[backtest-sigma-others-parquet-read-2026-04-30]]
    """

    def __init__(self, *, market_id: str, chain_ts: int, reason: str) -> None:
        self.market_id = market_id
        self.chain_ts = chain_ts
        self.reason = reason
        super().__init__(
            f"EmptyCompetitionPoolError: market_id={market_id!r} "
            f"chain_ts={chain_ts} reason={reason!r}"
        )
