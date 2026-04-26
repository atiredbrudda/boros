"""FILL-04: AMM consumption model (runtime analogue of DATA-05 ingest assertion).

Computes per-tick `amm_share(delta, t) = max(combined - raw, 0.0)` and asserts the
per-epoch runtime conservation identity.

Contract:
    book_ahead_end = book_ahead_start
                     - taker_consumption_ahead
                     - amm_consumption
                     + net_placements_ahead

Any violation raises AMMConsumptionIdentityError — must NOT be caught and
skipped. Defends PITFALLS §B3 at decision-engine call time (Phase 1 DATA-05 at
ingest time).

[[amm-consumption-model-v05]]
"""

from __future__ import annotations

import polars as pl
import structlog

from .schemas import AMMConsumptionIdentityError

log = structlog.get_logger(__name__)

# Re-export for convenience (Phase 4 DecisionEngine imports from here)
__all__ = [
    "AMMConsumptionIdentityError",
    "compute_amm_share_timeseries",
    "assert_epoch_conservation",
]


def compute_amm_share_timeseries(
    raw: pl.DataFrame,
    combined: pl.DataFrame,
    *,
    epoch_start_ts: int,
    epoch_end_ts: int,
) -> pl.DataFrame:
    """Compute amm_share(delta, t) = max(combined - raw, 0.0) per (snapshot_ts, tick).

    Filters both inputs to [epoch_start_ts, epoch_end_ts). Raises
    AMMConsumptionIdentityError if any (combined - raw) < -tolerance, mirroring
    the ingest-time assert_amm_conservation shape.

    Input schema:
        raw:      snapshot_ts | tick | size          (DATA-02 order_book_raw)
        combined: snapshot_ts | tick | size_combined (DATA-02 order_book_combined)

    Output schema:
        snapshot_ts | tick | amm_share
    """
    raw_sel = raw.filter((pl.col("snapshot_ts") >= epoch_start_ts) & (pl.col("snapshot_ts") < epoch_end_ts)).select(
        ["snapshot_ts", "tick", "size"]
    )
    combined_sel = combined.filter(
        (pl.col("snapshot_ts") >= epoch_start_ts) & (pl.col("snapshot_ts") < epoch_end_ts)
    ).select(["snapshot_ts", "tick", pl.col("size_combined")])

    joined = raw_sel.join(combined_sel, on=["snapshot_ts", "tick"], how="full", coalesce=True)
    joined = joined.with_columns(
        pl.col("size_combined").fill_null(0.0),
        pl.col("size").fill_null(0.0),
    )

    # Hard-fail on any negative combined-raw (below tolerance). Tolerance at 1e-9
    # because Phase 1 DATA-05 ingest already rounded; any negative here is a real bug.
    neg = joined.filter(pl.col("size_combined") - pl.col("size") < -1e-9)
    if not neg.is_empty():
        log.error(
            "fill_model.amm_conservation_violation",
            epoch_start=epoch_start_ts,
            epoch_end=epoch_end_ts,
            offending_rows=neg.head(5).to_dicts(),
            n_offending=neg.height,
        )
        raise AMMConsumptionIdentityError(
            f"combined < raw on {neg.height} (snapshot_ts, tick) pairs during "
            f"[{epoch_start_ts}, {epoch_end_ts}); first 5: {neg.head(5).to_dicts()}"
        )

    return joined.with_columns(
        pl.max_horizontal(pl.col("size_combined") - pl.col("size"), pl.lit(0.0)).alias("amm_share")
    ).select(["snapshot_ts", "tick", "amm_share"])


def assert_epoch_conservation(
    book_ahead_start: float,
    book_ahead_end: float,
    taker_consumption_ahead: float,
    amm_consumption: float,
    net_placements_ahead: float,
    *,
    epoch_start_ts: int,
    epoch_end_ts: int,
    tolerance: float = 1e-6,
) -> None:
    """Runtime per-epoch flow identity. Raises on violation.

    book_ahead_end ~= book_ahead_start
                      - taker_consumption_ahead
                      - amm_consumption
                      + net_placements_ahead

    Logs fill_model.amm_conservation_violation (error) BEFORE raising so
    the operator has a grep-joinable record by run_id.
    """
    expected = book_ahead_start - taker_consumption_ahead - amm_consumption + net_placements_ahead
    delta = book_ahead_end - expected
    if abs(delta) > tolerance:
        log.error(
            "fill_model.amm_conservation_violation",
            epoch_start=epoch_start_ts,
            epoch_end=epoch_end_ts,
            identity_delta=float(delta),
            book_ahead_start=float(book_ahead_start),
            book_ahead_end=float(book_ahead_end),
            taker_consumption_ahead=float(taker_consumption_ahead),
            amm_consumption=float(amm_consumption),
            net_placements_ahead=float(net_placements_ahead),
        )
        raise AMMConsumptionIdentityError(
            f"per-epoch conservation identity violated: delta={delta:.6g} > tolerance={tolerance}, "
            f"epoch=[{epoch_start_ts}, {epoch_end_ts}]"
        )
