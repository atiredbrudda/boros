---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
reviewed: 2026-04-24T00:00:00Z
depth: standard
files_reviewed: 43
files_reviewed_list:
  - python/src/boros_brain/data/__init__.py
  - python/src/boros_brain/data/chain_time.py
  - python/src/boros_brain/data/findex_reader.py
  - python/src/boros_brain/data/ingester/__init__.py
  - python/src/boros_brain/data/ingester/base.py
  - python/src/boros_brain/data/ingester/cli.py
  - python/src/boros_brain/data/ingester/exceptions.py
  - python/src/boros_brain/data/ingester/market_trades.py
  - python/src/boros_brain/data/ingester/order_book.py
  - python/src/boros_brain/data/ingester/schemas.py
  - python/src/boros_brain/data/ingester/settlement_md.py
  - python/src/boros_brain/data/ingester/underlying_apr.py
  - python/src/boros_brain/data/poller/__init__.py
  - python/src/boros_brain/data/poller/e_liq_poller.py
  - python/src/boros_brain/data/poller/markets_poller.py
  - python/src/boros_brain/data/poller/schemas.py
  - python/src/boros_brain/data/rest_client.py
  - python/src/boros_brain/data/rpc_client.py
  - python/src/boros_brain/duckdb_layer/__init__.py
  - python/src/boros_brain/duckdb_layer/setup.py
  - python/src/boros_brain/duckdb_layer/views.sql
  - python/src/boros_brain/logging/redaction.py
  - python/src/boros_brain/screener/__init__.py
  - python/src/boros_brain/screener/__main__.py
  - python/src/boros_brain/screener/cli.py
  - python/src/boros_brain/screener/economics_gate.py
  - python/src/boros_brain/screener/filter.py
  - python/src/boros_brain/screener/kill_report.py
  - python/src/boros_brain/screener/metrics.py
  - python/src/boros_brain/screener/report.py
  - python/src/boros_brain/screener/rescreen.py
  - python/src/boros_brain/screener/scale_calibration.py
  - python/src/boros_brain/state/migrations/versions/0002_reward_budget_history.py
  - python/src/boros_brain/state/schemas.sql
  - python/src/boros_brain/state/writers/clo_history.py
  - python/src/boros_brain/state/writers/reward_budget_history.py
  - scripts/architecture_lint.py
  - scripts/boros-brain-wrapper.sh
  - scripts/boros-hands-wrapper.sh
  - scripts/no_plain_keys.py
  - scripts/no_time_time_lint.py
  - scripts/probe_historical_budget.py
  - scripts/wiki_cite_lint.py
  - strategy/v0.5-default.yaml
findings:
  critical: 3
  warning: 4
  info: 3
  total: 10
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-24T00:00:00Z
**Depth:** standard
**Files Reviewed:** 43
**Status:** issues_found

## Summary

Phase 01 delivers the infrastructure spine, data ingestion pipeline, pollers, DuckDB analytical layer, screener, and economics gate. The architecture is generally sound: WAL-mode SQLite with single-writer discipline, RUN_MANIFEST on every CLI entry point, eventIndex enforcement, and explicit kill-switch guards are all well-implemented. However, there are three critical bugs that will crash at runtime plus four warning-level issues that can produce silent wrong answers.

The most serious issue is a mis-wired call signature for `ingest_order_book_combined` in the ingester CLI — it passes positional arguments where the function requires keyword-only arguments. This will `TypeError` on first use of `--kind order_book_combined`. The daily rescreen stage passes `--dest` to the ingester CLI, which only accepts `--out` — the subprocess will exit non-zero silently (absorbed by the returncode tolerance check). The third critical issue is `conn.commit()` called on a connection opened with `isolation_level=None` (autocommit) in `reward_budget_history.py` — the call is a no-op that misleads the reader about transaction semantics and will raise `ProgrammingError` in newer Python sqlite3 builds.

---

## Critical Issues

### CR-01: `ingest_order_book_combined` called with wrong positional arguments in ingester CLI

**File:** `python/src/boros_brain/data/ingester/cli.py:107`

**Issue:** The function signature is:
```python
def ingest_order_book_combined(
    ndjson_path: Path,
    raw_ndjson_path: Path | None = None,
    *,                       # keyword-only barrier
    market_id: str,
    tick_size: str,
    out_root: Path,
) -> IngestResult:
```
The CLI calls it as:
```python
result = ingest_order_book_combined(args.src, args.market_id, args.tick_size, out_root)
```
`args.market_id` (a string such as `"ETH"`) is passed as `raw_ndjson_path` (a `Path | None`). `args.tick_size` is the third positional argument, but `*` in the signature makes everything after it keyword-only — Python raises `TypeError: ingest_order_book_combined() takes from 1 to 2 positional arguments but 4 were given` on the first `--kind order_book_combined` invocation. `market_id`, `tick_size`, and `out_root` are never populated.

**Fix:**
```python
result = ingest_order_book_combined(
    args.src,
    market_id=args.market_id,
    tick_size=args.tick_size,
    out_root=out_root,
)
```

---

### CR-02: `rescreen.py` ingest stage passes `--dest` but ingester CLI only accepts `--out`

**File:** `python/src/boros_brain/screener/rescreen.py:62`

**Issue:** `_run_ingest_stage` builds the subprocess command using `"--dest"` as the output flag:
```python
"--dest",
"data/parquet/",
```
The ingester CLI at `data/ingester/cli.py:58` defines the flag as `--out` (`p.add_argument("--out", required=True, ...)`). There is no `--dest` argument. `argparse` exits with status 2 ("error: unrecognized arguments: --dest"), which is outside the allowed set `{0, 1}` that `_run_ingest_stage` treats as acceptable. Every ingest subprocess during daily rescreen will log a warning and skip, so the parquet data never refreshes.

Additionally, the loop runs all five kinds unconditionally without passing `--market-id` or `--exchange`, which are required for most kinds. This compounds the issue — even after fixing `--dest → --out`, every kind except a hypothetical bare invocation will also fail argparse validation.

**Fix:**
```python
# Replace --dest with --out, and gate each kind on its required args
result = subprocess.run(
    [
        sys.executable,
        "-m",
        "boros_brain.data.ingester.cli",
        "--kind", kind,
        "--src", "data/raw/",
        "--out", "data/parquet/",    # was --dest
        "--config", config_path,
        # Pass --market-id / --exchange per-kind as needed
    ],
    capture_output=True,
)
```
The right architectural fix is for `_run_ingest_stage` to enumerate specific input files with their required args (market_id, exchange) rather than blindly looping over all kinds with a single `data/raw/` path. The current design cannot work at all — `--src data/raw/` points to a directory, not a file, and `pl.read_ndjson` requires a file path.

---

### CR-03: `conn.commit()` called on an autocommit connection in `reward_budget_history.py`

**File:** `python/src/boros_brain/state/writers/reward_budget_history.py:68`

**Issue:** `insert_reward_budget_row` receives a `sqlite3.Connection` that was opened by the `ELiqPoller` constructor with `self.conn` — which is passed in by the caller. Looking at `db.open_connection`, it uses `isolation_level=None` (autocommit). In Python's `sqlite3` with `isolation_level=None`, the connection is in autocommit mode; every statement commits immediately. Calling `conn.commit()` on such a connection raises `ProgrammingError: cannot commit — no transaction is active` in Python 3.12+ (CPython changed this behavior). Even in older versions it is a no-op that creates a false expectation: the docstring says "callers are responsible for committing", but the writer both uses an externally-provided connection AND commits it, which violates the documented contract in `db.py` ("callers that want explicit transactions issue BEGIN/COMMIT directly").

More practically, `ELiqPoller` passes `self.conn` which is a plain `sqlite3.Connection` that the constructor receives — without going through `open_connection`. If that connection is in default transaction mode (not autocommit), the commit call is correct but the writer is now committing a transaction scope it doesn't own, which can prematurely commit partially-formed batches if `ELiqPoller` ever writes multiple rows in a single transaction.

**Fix:** Remove `conn.commit()` from `insert_reward_budget_row`. The writer must not manage commit lifecycle for an externally-provided connection. Per `db.py` docstring: the caller owns the transaction lifecycle. If the `ELiqPoller` wants each row committed immediately, it should call `conn.commit()` after `insert_reward_budget_row` returns, or open the connection with `isolation_level=None`.

```python
def insert_reward_budget_row(conn, *, market_id, e_liq_per_epoch, ...):
    ...
    conn.execute(
        "INSERT INTO reward_budget_history ...",
        (...),
    )
    # Do NOT call conn.commit() here — caller owns transaction lifecycle (db.py contract)
```

---

## Warnings

### WR-01: Scale calibration formula uses `clo_lower_thresh` only — `clo_upper_thresh` is ignored, and the formula silently produces wrong SCALE when `clo_lower_thresh == 10000.0`

**File:** `python/src/boros_brain/screener/scale_calibration.py:64-65`

**Issue:** The SCALE formula inverts `fIndex_display = 10000 + f_index_raw / SCALE` to get:
```python
s1 = p1.f_index_raw / (p1.clo_lower_thresh - 10000.0)
s2 = p2.f_index_raw / (p2.clo_lower_thresh - 10000.0)
```
Two problems:
1. If `clo_lower_thresh == 10000.0` (a valid tick-space value meaning the boundary is at exactly the center), the denominator is zero and Python produces `float('inf')` or `ZeroDivisionError`. There is no guard for this case.
2. The formula only uses `clo_lower_thresh`, never `clo_upper_thresh` despite storing it in `CalibrationPoint`. The research notes "two (clo, fIndex) data points resolve SCALE" — using only the lower bound leaves half the information unused and fails when the lower bound happens to equal 10000.

**Fix:**
```python
def calibrate_scale(p1: CalibrationPoint, p2: CalibrationPoint) -> ScaleResult:
    # Use both lower and upper for two independent estimates per point
    # Guard denominator against zero before dividing
    denom1 = p1.clo_lower_thresh - 10000.0
    denom2 = p2.clo_lower_thresh - 10000.0
    if denom1 == 0.0 or denom2 == 0.0:
        raise InsufficientCalibrationData(
            f"{p1.market_id}: clo_lower_thresh == 10000.0 — cannot invert SCALE formula"
        )
    s1 = p1.f_index_raw / denom1
    s2 = p2.f_index_raw / denom2
    ...
```

---

### WR-02: `r_apr_potential` computation in screener filter uses an unexplained magic divisor of `100.0`

**File:** `python/src/boros_brain/screener/filter.py:214`

**Issue:**
```python
r_apr_potential = float(budget_row[0]) * 52 / 100.0
```
`budget_row[0]` is `e_liq_per_epoch` (PENDLE/epoch from `reward_budget_history`). The formula multiplies by 52 (epochs/year) and divides by 100.0. The divisor `100.0` is not documented and does not match the DATA-09 formula in `economics_gate.py` which uses `required_collateral_pendle` as the denominator. The `100.0` appears to be a proxy for `$100 collateral` but:
- It embeds the assumption that 1 PENDLE = 1 USD (wrong)
- It hard-codes the $100 starting collateral as a magic number, which will silently give wrong comparisons when collateral changes
- The value is compared against `alt_yield + fill_loss_coarse_bound` in `economics_gate.py`, but the gate re-reads `r_apr_potential` from the JSON report and compares directly against the threshold without recomputing — meaning any unit confusion here propagates into the kill-switch decision

This is a latent version of checker issue #06 (PENDLE vs USD unit confusion) inside the screener itself.

**Fix:** Replace the magic `100.0` with a documented constant or config knob:
```python
# r_apr_potential: coarse estimate — PENDLE/epoch * 52 epochs/year / required_collateral_pendle
# required_collateral_pendle is TBD (Phase 3 price oracle). For Phase 1, note this is
# unit-inconsistent if e_liq_per_epoch is in PENDLE and collateral is in USD.
# TODO(Phase-3): replace 100.0 with config.screener.required_collateral_pendle
COLLATERAL_PHASE1_PROXY = 100.0  # noqa: naming — intentional placeholder
r_apr_potential = float(budget_row[0]) * EPOCHS_PER_YEAR / COLLATERAL_PHASE1_PROXY
```
Also import `EPOCHS_PER_YEAR` from `economics_gate` to avoid duplication.

---

### WR-03: Duplicate `model_config` assignment in `SyncStatus` Pydantic model — second assignment silently overwrites the first

**File:** `python/src/boros_brain/data/poller/schemas.py:28-33`

**Issue:**
```python
class SyncStatus(BaseModel):
    model_config = ConfigDict(extra="allow")           # line 28 — MISSING populate_by_name

    block_number: int = Field(alias="blockNumber")
    timestamp: int

    model_config = ConfigDict(extra="allow", populate_by_name=True)  # line 33 — overwrites line 28
```
The first `model_config` assignment on line 28 is immediately overwritten by the second on line 33. The net effect is correct (both end up with `extra="allow", populate_by_name=True`) but the dead first assignment is a code quality trap that can mislead a future editor who adds a field between lines 28 and 33 thinking they are working under a different config.

**Fix:** Remove the first `model_config` assignment (line 28):
```python
class SyncStatus(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    block_number: int = Field(alias="blockNumber")
    timestamp: int
```

---

### WR-04: `MarketsPoller.tick()` creates a new `AsyncWeb3 + AsyncHTTPProvider` instance per market per tick cycle via lazy `make_arbitrum_rpc`

**File:** `python/src/boros_brain/data/poller/markets_poller.py:140-147`

**Issue:** When `findex_readers` is not pre-wired (the default in `run_markets_poller`), each new market symbol encountered triggers:
```python
w3 = await make_arbitrum_rpc(self.config)
reader = FIndexReader(w3=w3, ...)
self._findex_readers[symbol] = reader
```
`make_arbitrum_rpc` creates a brand-new `AsyncWeb3(AsyncHTTPProvider(...))` per call. `AsyncHTTPProvider` maintains an underlying aiohttp session. These sessions are never explicitly closed — the `MarketsPoller` has no `close()` or `__aenter__`/`__aexit__`. Over a long-running session this leaks one unclosed aiohttp client session per unique market symbol encountered for the first time.

In practice this is bounded (typically 3 markets in scope), so it will not accumulate unboundedly. However the resource leak is still present: at process exit, aiohttp will log "Unclosed client session" warnings to stderr, and the underlying TCP connections will not be cleanly shut down.

**Fix:** Accept a shared `w3: AsyncWeb3` in `MarketsPoller.__init__` and use it instead of lazy-creating per market:
```python
def __init__(self, config, http, run_id, w3=None, findex_readers=None, ...):
    self._w3 = w3  # shared; caller owns lifecycle
    ...

# In tick():
if reader is None:
    if self._w3 is None:
        raise RuntimeError("w3 not wired — pass w3= to MarketsPoller or pre-populate findex_readers")
    reader = FIndexReader(w3=self._w3, oracle_address=findex_oracle_addr, ...)
```

---

## Info

### IN-01: `now_cached()` return is `int | None` but the return type annotation says `int`

**File:** `python/src/boros_brain/data/chain_time.py:124`

**Issue:**
```python
async def now_cached(self) -> int:
    ...
    except TimeoutError:
        log.warning("chain_time.rpc_timeout", ...)
        # Return stale cached value — do NOT halt on transient timeout.
return self._value  # type: ignore[return-value]
```
`self._value` can be `None` if the cache has never been populated (cold start) and the first RPC call times out. The `# type: ignore[return-value]` suppresses the type error instead of handling the case. A caller that uses the result as `int` (e.g., `cutoff_ts = now - ...`) will get `TypeError: unsupported operand type(s) for -: 'NoneType' and 'int'` on first use after a cold-start timeout.

This is an edge case (cold start + immediate timeout), but it can occur in test environments or when the RPC endpoint is down before the bot has populated the cache.

**Fix:**
```python
async def now_cached(self) -> int:
    ...
    except TimeoutError:
        if self._value is None:
            raise RuntimeError(
                "chain_time.rpc_timeout on cold cache — no cached value to return"
            ) from None
        log.warning("chain_time.rpc_timeout", last_value=self._value, stale=True)
    return self._value  # guaranteed non-None here
```

---

### IN-02: `screener/filter.py` order-book SQL query selects a `size` column that does not exist in `order_book_combined` parquet

**File:** `python/src/boros_brain/screener/filter.py:153-163`

**Issue:** The screener SQL query:
```sql
SELECT snapshot_ts, market_id, tick_size, tick, size
FROM order_book_combined
```
The `order_book_combined` parquet written by the ingester (`order_book.py`) uses the column name `sz_combined_float`, not `size`. The column `size` does not exist in the parquet schema. DuckDB will raise `BinderException: Referenced column "size" not found` when this query executes with real parquet data.

The downstream `metrics.py:173` functions then access `edge["size"]` on the resulting DataFrame, compounding the issue.

**Fix:** Either rename the parquet column at write time (`sz_combined_float → size`) or alias it in the SQL:
```sql
SELECT snapshot_ts, market_id, tick_size, tick, sz_combined_float AS size
FROM order_book_combined
```
Similarly, the `market_trades` SQL on line 100 queries `size` — this column is renamed to `size_float` by the ingester's `_parse_size_column`, so the correct column name is `size_float`.

---

### IN-03: `screener/filter.py` order-book SQL query references `size` from `market_trades` but the ingester drops and renames that column

**File:** `python/src/boros_brain/screener/filter.py:100`

**Issue:** The screener queries:
```sql
SELECT blockTimestamp, eventIndex, datetime, rate, side, size, txHash, market_id
FROM market_trades
```
The `market_trades` ingester (`market_trades.py`) drops the raw `size` column via `df.drop("size")` and replaces it with `size_float` and `size_wei`. The column `size` does not exist in the parquet output. DuckDB will raise `BinderException` when real data is present.

**Fix:** Change the SQL to reference the renamed column:
```sql
SELECT blockTimestamp, eventIndex, datetime, rate, side, size_float AS size, txHash, market_id
FROM market_trades
```
(Using `size_float AS size` preserves the downstream DataFrame column name `size` used by `compute_realized_vol`, `compute_reversal_count`, etc., which do not reference size directly — but better to alias explicitly than leave ambiguity.)

---

_Reviewed: 2026-04-24T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
