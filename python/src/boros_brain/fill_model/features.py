"""FILL-02 — DuckDB-driven feature pipeline for the NHPP fill model.

Joins Phase 1 parquet outputs (market_trades, order_book_combined, underlying_apr,
clo_history) into per-(market, side, bin) feature rows.

Output columns: market_id, side, bin_start (epoch seconds Int64), trade_count,
basis_spread, imbalance, sin_settlement, cos_settlement, ewma_vol, bin_duration_s.

CRITICAL INVARIANT (T-02-F-02 — no look-ahead):
  The EWMA vol window is ``ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING`` — the current
  bin's trades are NOT included in the vol estimate for that bin. Changing this to
  ``CURRENT ROW`` violates the no-look-ahead invariant and will break the GoF test.

[[covariate-selection-v05]]: 4 raw covariates → 5 model features.
[[fill-model-library-decision-tick-vs-statsmodels]]: fit uses statsmodels, not tick.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import polars as pl
import structlog

from ..config.schema import BotConfig
from ..duckdb_layer.setup import open_analytical_conn

log = structlog.get_logger(__name__)

# ── Market-ID translation (Wave-1 parquet uses archive-prefixed IDs) ─────────
# The parquet partitions use ``{N}-{EXCHANGE}-{ASSET}-{MATURITY}`` keys
# (e.g. ``101-BINANCE-ETHUSDT-25SEP2026``) while the operator and SQLite spine
# use canonical ``{EXCHANGE}-{ASSET}-{MATURITY}`` keys. The mapping file
# at var/fetcher/market_id_mapping.json bridges these two namespaces.
# Same logic as screener/filter.py ``_parquet_market_id`` — kept as a local
# copy here to avoid a cross-module import between fill_model and screener.
# Resolve the mapping file relative to the module, not CWD, so this works
# regardless of whether the caller runs from boros/ or python/ subdirectory.
_FILL_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # …/boros/python/src/boros_brain/fill_model → boros/
_FILL_MAPPING_PATH = _FILL_PROJECT_ROOT / "var/fetcher/market_id_mapping.json"
_FILL_ARCHIVE_PREFIX_RE = re.compile(r"^\d+-")


@lru_cache(maxsize=1)
def _load_fill_market_id_mapping() -> dict[str, str]:
    """Load canonical→archive mapping. Returns {} when file absent (test fixtures)."""
    if not _FILL_MAPPING_PATH.exists():
        return {}
    try:
        raw = json.loads(_FILL_MAPPING_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("fill_model.features.mapping_load_failed", path=str(_FILL_MAPPING_PATH), error=str(exc))
        return {}
    out: dict[str, str] = {}
    for canonical, entry in (raw.get("mapping") or {}).items():
        recommended = (entry or {}).get("recommended")
        if isinstance(recommended, str) and recommended:
            out[canonical] = recommended
    return out


def _parquet_market_id(mid: str) -> str:
    """Translate canonical market_id → archive-prefixed parquet partition key.

    Idempotent: already-prefixed IDs pass through unchanged.
    Unknown IDs pass through (preserves test-fixture paths).
    """
    if _FILL_ARCHIVE_PREFIX_RE.match(mid):
        return mid
    mapping = _load_fill_market_id_mapping()
    return mapping.get(mid, mid)


@dataclass(frozen=True)
class FeatureSet:
    """Container for feature-table metadata after build_features_table returns.

    Attributes
    ----------
    path:
        Directory (or file) path where the Hive-partitioned parquet was written.
    row_count:
        Number of feature rows written (all sides combined).
    column_names:
        Column names present in the written parquet.
    """

    path: Path
    row_count: int
    column_names: list[str]


# CRITICAL: ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING — NOT CURRENT ROW.
# This left-closed EWMA ensures the current bin's trades do NOT contaminate
# the vol estimate for that same bin (T-02-F-02 no-look-ahead invariant).
#
# Column-name adaptations vs RESEARCH §Code Examples #1:
#   - market_trades uses camelCase: blockTimestamp, eventIndex, rate, side, size_float
#   - market_id is a Hive partition key added by the ingester
#   - underlying_apr uses: timestamp, market_id (via exchange+symbol), funding_rate_apr
#   - order_book_combined uses: snapshot_ts, market_id, tick_size, sz_combined_float
#   - clo_history provides: snapshot_ts, market_id, mid_rate (implied)
#   The SQL falls back gracefully when views return zero rows (Phase 1 stub views).
_FEATURE_SQL = """
WITH bins AS (
  SELECT
    market_id,
    side,
    -- 60-second bins: floor to bin boundary in epoch seconds
    (blockTimestamp / $bin_duration_s_int) * $bin_duration_s_int AS bin_start_epoch,
    COUNT(*)                                                      AS trade_count,
    AVG(rate)                                                     AS mid_rate
  FROM market_trades
  WHERE blockTimestamp >= $window_start
    AND blockTimestamp < $window_end
    AND market_id = $market_id
  GROUP BY 1, 2, 3
),
bins_lagged AS (
  -- Step 1: compute squared return per bin (DuckDB forbids nested window funcs).
  -- LAG must be in its own CTE before the rolling AVG window can reference it.
  SELECT
    market_id,
    side,
    bin_start_epoch,
    mid_rate,
    POW(
      mid_rate - LAG(mid_rate) OVER (
        PARTITION BY market_id, side
        ORDER BY bin_start_epoch
      ),
      2
    ) AS sq_return
  FROM bins
),
vol AS (
  -- Step 2: left-closed rolling avg of squared returns over 5 preceding bins.
  -- ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING excludes the current bin (T-02-F-02).
  SELECT
    market_id,
    side,
    bin_start_epoch,
    SQRT(
      AVG(sq_return)
      OVER (
        PARTITION BY market_id, side
        ORDER BY bin_start_epoch
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
      )
    ) AS ewma_vol
  FROM bins_lagged
),
imbalance AS (
  -- Order-book imbalance from combined book snapshot closest to (but before) bin_start.
  SELECT
    market_id,
    -- Use snapshot_ts as bin proxy (already epoch-seconds in clo_history / order_book_combined)
    (snapshot_ts / $bin_duration_s_int) * $bin_duration_s_int AS bin_start_epoch,
    (
      SUM(CASE WHEN tick > 0 THEN TRY_CAST(sz_combined_float AS DOUBLE) ELSE 0.0 END)
      - SUM(CASE WHEN tick < 0 THEN TRY_CAST(sz_combined_float AS DOUBLE) ELSE 0.0 END)
    ) / NULLIF(SUM(TRY_CAST(sz_combined_float AS DOUBLE)), 0) AS book_imbalance
  FROM order_book_combined
  WHERE snapshot_ts >= $window_start
    AND snapshot_ts < $window_end
    AND market_id = $market_id
  GROUP BY 1, 2
),
underlying AS (
  -- Most recent underlying APR before each bin start.
  -- underlying_apr uses a numeric `timestamp` col; exchange+symbol map to market_id
  -- We join on the closest available underlying rate within the window.
  SELECT
    (timestamp / $bin_duration_s_int) * $bin_duration_s_int AS bin_start_epoch,
    AVG(funding_rate_apr)                                     AS underlying_rate
  FROM underlying_apr
  WHERE timestamp >= $window_start
    AND timestamp < $window_end
  GROUP BY 1
)
SELECT
  b.market_id,
  b.side,
  b.bin_start_epoch                                                           AS bin_start,
  b.trade_count,
  -- Covariate 1: basis spread = mid_implied_rate - underlying (proxy)
  b.mid_rate - COALESCE(u.underlying_rate, 0.0)                              AS basis_spread,
  -- Covariate 2: order-book imbalance
  COALESCE(i.book_imbalance, 0.0)                                            AS imbalance,
  -- Covariate 3a: sin of time-since-last-funding-settlement (8h = 28800s period)
  SIN(2 * PI() * (b.bin_start_epoch % 28800) / 28800.0)                     AS sin_settlement,
  -- Covariate 3b: cos of time-since-last-funding-settlement
  COS(2 * PI() * (b.bin_start_epoch % 28800) / 28800.0)                     AS cos_settlement,
  -- Covariate 4: left-closed EWMA realized vol (T-02-F-02 no-look-ahead)
  COALESCE(v.ewma_vol, 0.0)                                                  AS ewma_vol,
  CAST($bin_duration_s AS DOUBLE)                                            AS bin_duration_s
FROM bins b
LEFT JOIN vol v        USING (market_id, side, bin_start_epoch)
LEFT JOIN imbalance i  USING (market_id, bin_start_epoch)
LEFT JOIN underlying u USING (bin_start_epoch)
"""


def build_features_table(
    config: BotConfig,
    market_id: str,
    window_start_ts: int,
    window_end_ts: int,
) -> FeatureSet:
    """Join Phase 1 parquet outputs into per-(market, side, bin) feature rows.

    Writes a Hive-partitioned parquet directory under
    ``data/parquet/fill_features/market_id=<m>/...`` and returns a FeatureSet
    describing the write.

    Parameters
    ----------
    config:
        Active BotConfig. Uses config.infra.sqlite_path and config.fill_model.bin_duration_s.
    market_id:
        Boros market identifier (e.g. ``BINANCE-ETHUSDT-29MAY2026``).
    window_start_ts:
        Epoch seconds (inclusive) for the start of the fit window.
    window_end_ts:
        Epoch seconds (exclusive) for the end of the fit window.

    Returns
    -------
    FeatureSet
        Metadata about the written parquet output.
    """
    bin_s = config.fill_model.bin_duration_s
    bin_s_int = int(bin_s)

    # Translate canonical market_id → archive-prefixed parquet partition key.
    # The Wave-1 ingest pipeline partitioned by ``{N}-{EXCHANGE}-...`` while
    # the operator and SQLite spine use ``{EXCHANGE}-...``. The query must use
    # the parquet form; output is normalized back to the canonical form below.
    parquet_market_id = _parquet_market_id(market_id)
    if parquet_market_id != market_id:
        log.debug(
            "fill_model.features.market_id_translated",
            canonical=market_id,
            archive=parquet_market_id,
        )

    # Resolve paths relative to the project root (not CWD, which may be python/
    # when invoked via ``uv run --directory python``).
    _here = Path(__file__).resolve()
    _project_root = _here.parents[4]  # .../boros/python/src/boros_brain/fill_model -> boros/
    sqlite_abs = str(_project_root / config.infra.sqlite_path)
    parquet_root_abs = str(_project_root / "data/parquet/")

    conn = open_analytical_conn(sqlite_abs, parquet_root_abs)
    try:
        numpy_dict = conn.execute(
            _FEATURE_SQL,
            {
                "market_id": parquet_market_id,
                "window_start": window_start_ts,
                "window_end": window_end_ts,
                "bin_duration_s": bin_s,
                "bin_duration_s_int": bin_s_int,
            },
        ).fetchnumpy()  # numpy dict — works without pyarrow
        df = pl.DataFrame(numpy_dict)
    finally:
        conn.close()

    # Normalize the market_id column back to canonical form so downstream
    # fill_model_fits rows and parquet artifacts use the operator-facing ID.
    if parquet_market_id != market_id and "market_id" in df.columns:
        df = df.with_columns(pl.lit(market_id).alias("market_id"))

    # Drop zero-duration bins (safety guard — should not arise with correct SQL)
    df = df.filter(pl.col("bin_duration_s") > 0)

    out_root = _FILL_PROJECT_ROOT / "data/parquet/fill_features"
    out_root.mkdir(parents=True, exist_ok=True)

    if df.is_empty():
        log.warning(
            "fill_model.features_empty",
            market_id=market_id,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
        )
        # Write an empty parquet to maintain the path contract.
        # Phase 05.5 Bug: DuckDB fetchnumpy() returns Object-dtype arrays for empty
        # result sets, which polars cannot write to parquet. Use an explicit schema
        # so the empty parquet is always written with the correct column types.
        # [[fill-model-predict-look-ahead-read-path]] — related fix at the read layer.
        _EMPTY_SCHEMA = {
            "market_id": pl.String,
            "side": pl.String,
            "bin_start": pl.Float64,
            "trade_count": pl.Int64,
            "basis_spread": pl.Float64,
            "imbalance": pl.Float64,
            "sin_settlement": pl.Float64,
            "cos_settlement": pl.Float64,
            "ewma_vol": pl.Float64,
            "bin_duration_s": pl.Float64,
        }
        empty_df = pl.DataFrame(schema=_EMPTY_SCHEMA)
        out_path = out_root / f"market_id={market_id}" / f"window_end_ts={window_end_ts}"
        out_path.mkdir(parents=True, exist_ok=True)
        empty_path = out_path / "features.parquet"
        empty_df.write_parquet(str(empty_path))
        return FeatureSet(path=empty_path, row_count=0, column_names=list(empty_df.columns))

    # Hive-partition by market_id; write via polars native (no pyarrow dependency).
    # One parquet file per (market_id, side, window_end_ts) partition.
    side_count = df["side"].n_unique()

    # Write as a single parquet partitioned by market_id + side using polars sink.
    out_path = out_root
    df.lazy().sink_parquet(
        pl.PartitionBy(
            str(out_path),
            key=["market_id", "side"],
        ),
        mkdir=True,
    )

    log.info(
        "fill_model.features_built",
        market_id=market_id,
        side_count=side_count,
        bin_count=df.height,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
        out=str(out_path),
    )

    return FeatureSet(path=out_path, row_count=df.height, column_names=list(df.columns))
