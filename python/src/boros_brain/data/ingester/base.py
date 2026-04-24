"""Shared ingester primitives — IngestResult, IngesterSchemaViolation, write_partitioned_parquet.

Uses polars `sink_parquet` with `pl.PartitionBy` for Hive-style partitioning.
pyarrow is intentionally NOT imported — it is not in the project's dependency
manifest. All Hive partitioning is done via polars' native streaming sink.

T-01-08-01 (Tampering — extreme values): callers use `.cast(strict=True)` to let
polars raise on overflow before this writer is called.

T-01-08-03 (DoS — large files): `sink_parquet` is streaming-friendly; each call
processes one file-worth of data. The 1 GB/file guidance is documented in the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import structlog

log = structlog.get_logger(__name__)


class IngesterSchemaViolation(RuntimeError):
    """Raised when NDJSON row fails a hard-fail schema assertion (e.g., missing eventIndex).

    Per DATA-01 spec + PITFALL §B2: eventIndex null/missing on ANY market_trades row
    causes ingest to stop loudly. This is not a soft-counted assertion_failure —
    it is a hard stop.
    """


@dataclass(frozen=True)
class IngestResult:
    """Summary returned by every ingester function."""

    rows_in: int
    rows_written: int
    path_out: str
    eventIndex_missing: int = 0
    assertion_failures: int = 0


def write_partitioned_parquet(
    df: pl.DataFrame,
    out_root: Path,
    partition_cols: list[str],
    subdir: str,
) -> Path:
    """Write DataFrame as Hive-partitioned parquet under out_root/subdir/.

    Uses polars native `sink_parquet` with `pl.PartitionBy` — no pyarrow dependency.
    Returns the directory path written to.

    Raises ValueError if any partition_col is not in df.columns (T-01-08-01:
    prevents silent schema drift from creating unreadable parquet).
    """
    missing = [c for c in partition_cols if c not in df.columns]
    if missing:
        raise ValueError(f"partition_cols {missing} not present in df columns {df.columns!r}")
    full = Path(out_root) / subdir
    full.mkdir(parents=True, exist_ok=True)

    # Use streaming sink with PartitionBy for Hive-style directory layout.
    # include_key=True (default) keeps partition cols in the parquet files as well
    # as in the directory names — required for hive_partitioning=True readback.
    df.lazy().sink_parquet(
        pl.PartitionBy(str(full), key=partition_cols),
        mkdir=True,
    )

    log.info(
        "ingester.parquet_written",
        path=str(full),
        rows=df.height,
        partitions=partition_cols,
    )
    return full
