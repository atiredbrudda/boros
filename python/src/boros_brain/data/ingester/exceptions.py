"""Ingester-specific exceptions."""

from __future__ import annotations


class AMMConservationError(RuntimeError):
    """Raised when combined_size(delta) - raw_book_size(delta) < 0 for any tick.

    PITFALLS §B3. This is a loud failure — do NOT catch and skip.

    Formula: combined_size(delta) - raw_book_size(delta) >= 0 for every tick delta.
    Violation means the AMM share accounting is broken; any fill-probability model
    downstream will be silently poisoned if this is not caught.
    """
