"""Operator-manual calibration CLI helper (LOCKED D-01 2026-04-24).

Called by `python -m boros_brain.reward_model calibrate ...` at daily re-screen
to refresh per-market `E_liq_per_epoch_pendle` + long/short side splits from
the Pendle dApp UI (or `team_statement` / `pendle_docs` fallback sources).

Validation flow:
  1. Pydantic MarketRewardCalibration constructor — fires P3-4 split-sum
     field_validator BEFORE any DB round-trip. Operator typos
     (`--long-split 0.6 --short-split 0.5`) caught here with a clear error.
  2. Writer-layer guard — same checks belt-and-braces.
  3. SQL CHECK constraints — last line of defense.

See [[market-reward-calibration-operator-workflow]] for the operator runbook.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from ..config.schema import MarketRewardCalibration
from ..state.writers.market_reward_calibration import (
    insert_market_reward_calibration,
)

log = structlog.get_logger(__name__)

__all__ = ["insert_operator_calibration"]


def insert_operator_calibration(
    sqlite_path: Path,
    *,
    market_id: str,
    e_liq_per_epoch_pendle: float,
    long_side_split: float,
    short_side_split: float,
    source: str,
    run_id: str,
) -> None:
    """Validate via Pydantic THEN persist via single-writer.

    Pydantic catches P3-4 (split sum != 1.0) BEFORE the DB layer.
    """
    calibrated_at_utc = datetime.now(UTC).isoformat()

    # Pydantic validation (P3-4 guard fires here).
    _ = MarketRewardCalibration(
        e_liq_per_epoch_pendle=e_liq_per_epoch_pendle,
        long_side_split=long_side_split,
        short_side_split=short_side_split,
        calibrated_at_utc=calibrated_at_utc,
        source=source,  # type: ignore[arg-type]  # narrowed to Literal in writer
    )

    # Persist (writer also validates — belt-and-braces).
    insert_market_reward_calibration(
        sqlite_path,
        market_id=market_id,
        e_liq_per_epoch_pendle=e_liq_per_epoch_pendle,
        long_side_split=long_side_split,
        short_side_split=short_side_split,
        calibrated_at_utc=calibrated_at_utc,
        source=source,  # type: ignore[arg-type]
        run_id=run_id,
    )

    log.info(
        "reward_model.operator_calibration_persisted",
        market_id=market_id,
        e_liq_per_epoch_pendle=e_liq_per_epoch_pendle,
        long_side_split=long_side_split,
        short_side_split=short_side_split,
        source=source,
        run_id=run_id,
    )
