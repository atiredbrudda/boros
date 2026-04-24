---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
plan: "09"
subsystem: data
tags: [python, httpx, pydantic, web3, sqlite, asyncio, boros-rest, findex-oracle]

# Dependency graph
requires:
  - phase: 01-01
    provides: BotConfig schema with DataConfig.boros_rest_base, markets_poll_interval_s, chain_time_cache_ttl_s
  - phase: 01-02
    provides: clo_history table schema + open_connection contextmanager + insert_* writer convention
  - phase: 01-03
    provides: structlog JSON logger with run_id bound via contextvars
  - phase: 01-04
    provides: docs/architecture.yml + pre-commit architecture lint
  - phase: 01-07
    provides: make_arbitrum_rpc AsyncWeb3 factory + chain_time.now_cached()
provides:
  - Real /markets response sample (docs/samples/markets-response.json, 58 KB, 30 markets)
  - A5 schema reconciliation notes (docs/samples/markets-schema-notes.md)
  - Shared httpx factory make_boros_rest_client + BorosApiError (data/rest_client.py)
  - Pydantic v2 MarketsResponse/Market/MarketConfig schemas matching real API shape (data/poller/schemas.py)
  - DATA-06 MarketsPoller with change-only clo_history writes + 5xx backoff (data/poller/markets_poller.py)
  - Single-writer clo_history helper insert_clo_history + insert_clo_snapshot (state/writers/clo_history.py)
  - DATA-07 FIndexReader with bytes32 decode, int112 sign extension, 1s TTL cache (data/findex_reader.py)
  - Pure-function decode_findex_bytes + fIndex_display + KNOWN_ORACLES + FINDEX_ABI exports
affects:
  - 01-10 (reward-budget poller — uses rest_client + insert pattern)
  - 01-11 (SCALE calibration — reads clo_history + f_index_raw pairs ≥1 day apart)
  - 01-12 (economics gate DATA-09 — uses FIndexReader.latest_annualized_rate())
  - Phase 2 fill model — MarketsPoller feeds clo_history for CLO drift detection
  - Phase 4 SAFE-02 — FIndexReader.get_latest_fIndex()['fTime'] vs chain_time.now_cached() for staleness

# Tech tracking
tech-stack:
  added:
    - httpx (AsyncClient factory wrapping Boros REST base_url + timeout)
    - web3.py eth.contract() with FINDEX_ABI for on-chain fIndexOracle reads
  patterns:
    - change-only clo_history writes: compare (clo_lower, clo_upper, f_index_raw) tuple before inserting
    - lazy per-market FIndexReader creation keyed by imData.symbol
    - bytes32 → bytes26 decode via val >> 48 (discard 6-byte zero padding; NOT raw[-26:])
    - int112 sign extension: if floatingIndex >= 2^111, subtract 2^112
    - pure-function decode isolated from RPC so it is unit-testable without a live connection
    - 1s TTL cache in FIndexReader (time.monotonic based; avoids sub-second RPC flood)
    - exponential backoff [base, 2x, 4x] + jitter on 5xx, 3 attempts max

key-files:
  created:
    - docs/samples/markets-response.json
    - docs/samples/markets-schema-notes.md
    - python/src/boros_brain/data/rest_client.py
    - python/src/boros_brain/data/poller/__init__.py
    - python/src/boros_brain/data/poller/schemas.py
    - python/src/boros_brain/data/poller/markets_poller.py
    - python/src/boros_brain/data/findex_reader.py
    - python/tests/test_markets_response_schema.py
    - python/tests/test_markets_poller.py
    - python/tests/test_findex_decode.py
    - python/tests/test_findex_reader.py
    - python/tests/fixtures/markets_response_fixture.json
  modified:
    - python/src/boros_brain/state/writers/clo_history.py
    - docs/architecture.yml
    - docs/ARCHITECTURE.md

key-decisions:
  - "Use imData.symbol (e.g. BINANCE-ETHUSDT-29MAY2026) as clo_history.market_id, not the integer marketId field — A5 reconciliation finding"
  - "decode_findex_bytes uses val>>48 (discard 6-byte low padding) — not raw[-26:] which the plan's RESEARCH snippet had wrong (confirmed against boros_bot_guide.md L206 and live oracle)"
  - "clo_history writer gained insert_clo_snapshot(conn,...) low-level sibling alongside insert_clo_history(path,...) for tests that manage their own connection lifecycle"
  - "MarketsPoller keyed by imData.symbol, not marketId int, to match KNOWN_ORACLES dict and DB convention"

patterns-established:
  - "A5-reconcile-first pattern: curl real endpoint + build schema against capture before writing any poller code"
  - "bytes32 decode pattern: val>>48 discard zero pad, then bit-field extraction with int112 sign extension"
  - "Change-only write discipline: compare full (lower, upper, findex_raw) tuple, write only on diff"

requirements-completed: [DATA-06, DATA-07]

# Metrics
duration: unknown (retroactively documented)
completed: "2026-04-24"
---

# Phase 01 Plan 09: /markets Poller + fIndexOracle Reader Summary

**Real /markets API captured (58 KB, 30 markets), A5 schema landmine closed, DATA-06 MarketsPoller + DATA-07 FIndexReader shipped with bytes32 decode verified against boros_bot_guide.md L206**

## Performance

- **Duration:** Unknown (retroactively documented — SUMMARY.md was never created at execution time)
- **Started:** Unknown
- **Completed:** 2026-04-24
- **Tasks:** 3 (Task 1: A5 capture + reconcile; Task 2: REST client + poller + schemas; Task 3: fIndexOracle reader)
- **Files modified:** ~16

## Accomplishments

- A5 landmine closed: real `/markets` response captured (58 KB, 30 markets); schema was `{results: [...]}` not bare list; CLO thresholds nested under `config.*`; `marketId` is int (not string); all differences documented and Pydantic schema built against real capture
- DATA-06 complete: `MarketsPoller` polls on 30s cadence, validates with `MarketsResponse` Pydantic v2 schema, decodes `floatingIndex` via per-market `FIndexReader`, writes `clo_history` rows change-only, retries on 5xx with exponential backoff
- DATA-07 complete: `decode_findex_bytes` pure function implements bytes32 decode per `boros_bot_guide.md L206` (`val>>48` to discard 6-byte zero pad; int112 sign extension); `FIndexReader` dataclass wraps it with 1s TTL cache and `latestAnnualizedRate()` accessor

## Task Commits

Each task committed atomically (TDD RED/GREEN pattern for Tasks 2–3):

1. **Task 1: Capture real /markets response + reconcile A5 schema landmine** - `9c96374` (feat)
2. **Task 2 RED: Failing tests for MarketsPoller + MarketsResponse schema** - `f0ebe30` (test)
3. **Task 2 GREEN: REST client + MarketsPoller + findex_reader skeleton** - `979e11c` (feat)
4. **Task 3 GREEN: fIndexOracle bytes32 decode + FIndexReader TTL cache** - `720543c` (feat)

_Plan checker reconciliation commit (pre-implementation):_ `162c517`
_Plan file commit:_ `b1551eb`

## Files Created/Modified

- `docs/samples/markets-response.json` — Real captured Boros /markets response (58 KB, 30 markets, 2026-04-24)
- `docs/samples/markets-schema-notes.md` — A5 reconciliation: field-by-field schema map + parse/log/ignore decisions
- `python/src/boros_brain/data/rest_client.py` — `make_boros_rest_client(config)` factory + `BorosApiError`
- `python/src/boros_brain/data/poller/__init__.py` — Empty package init (Wave 2 will add E_liq poller here)
- `python/src/boros_brain/data/poller/schemas.py` — Pydantic v2 `MarketsResponse`, `Market`, `MarketConfig`, `MarketImData`, `MarketExtConfig`, `MarketData`, `SyncStatus`
- `python/src/boros_brain/data/poller/markets_poller.py` — `MarketsPoller` class + `run_markets_poller` long-running task
- `python/src/boros_brain/data/findex_reader.py` — `decode_findex_bytes`, `fIndex_display`, `FIndexReader`, `FINDEX_ABI`, `KNOWN_ORACLES`, `FIndexDecodeError`
- `python/src/boros_brain/state/writers/clo_history.py` — `insert_clo_history(path,...)` + `insert_clo_snapshot(conn,...)` (low-level sibling added for test ergonomics)
- `python/tests/test_markets_response_schema.py` — Schema validation tests against real capture + fixture
- `python/tests/test_markets_poller.py` — Poller behaviour: first-write, no-write-on-same, CLO-change write, findex-change write, findex-decode-failure (null), 5xx backoff
- `python/tests/test_findex_decode.py` — Pure-function tests: zero payload, known synthetic, negative sign extension, fTime extraction, wrong-length rejection
- `python/tests/test_findex_reader.py` — TTL cache tests + live-RPC smoke test (skipped on CI)
- `python/tests/fixtures/markets_response_fixture.json` — Deterministic test fixture matching real response shape
- `docs/architecture.yml` — Nodes + edges for data.rest_client, data.poller.markets_poller, data.findex_reader, state.writers.clo_history
- `docs/ARCHITECTURE.md` — Mermaid diagram updated

## A5 Landmine Outcome (Task 1)

The `/markets` response shape was **significantly different** from planning assumptions:

| Assumption | Reality | Impact |
|-----------|---------|--------|
| Bare JSON array `[{...}]` | Wrapped: `{results:[...], total, skip, syncStatus}` | Schema field `results` not `markets` |
| `marketId: str` (e.g. "ETH-29MAY2026") | `marketId: int` (e.g. 74) | Use `imData.symbol` as DB market_id |
| `cloLowerThresh: float` at top level | `config.cloLowerThresh: int` (nested) | Access via `m.config.clo_lower_thresh` |
| `fIndexOracle: str` at top level | `config.fIndexOracle: str` (nested) | Access via `m.config.findex_oracle` |
| `takerFee: float` (percentage) | `config.takerFee: str` (1e18 string) | Decode as `int(v)/1e18` when needed |

All three `KNOWN_ORACLES` addresses from RESEARCH.md confirmed correct in the captured response.

## bytes32 Decode Deviation (Task 3)

The RESEARCH.md §Pattern 8 decode snippet used `raw[-26:]` (bottom 26 bytes). This is **incorrect** — the struct is packed in the **upper** 26 bytes, with 6 bytes of zero-padding at the bottom. The `boros_bot_guide.md L206` is authoritative: `val208 = int.from_bytes(raw, "big") >> 48`. The implementation follows the bot guide and confirmed correct layout in the schema notes.

## Decisions Made

- **`imData.symbol` as market_id string:** The API `marketId` is an integer; all DB columns, KNOWN_ORACLES dict, and poller cache use `imData.symbol` (e.g. `"BINANCE-ETHUSDT-29MAY2026"`) as the canonical string identifier.
- **`decode_findex_bytes` uses `val>>48`:** Corrects RESEARCH.md `raw[-26:]` snippet; boros_bot_guide.md L206 is the authoritative source; confirmed against live oracle output.
- **`insert_clo_snapshot` added as low-level sibling:** Tests that manage their own connection lifecycle (e.g. using a pre-seeded SQLite fixture) use `insert_clo_snapshot(conn, ...)` directly; production code uses `insert_clo_history(path, ...)` which opens its own connection via `open_connection()`.
- **`extra='allow'` on all Pydantic models:** T-01-09-01 mitigation — API schema drift adds fields without breaking validation; new fields logged at INFO by poller.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected bytes32 decode from `raw[-26:]` to `val>>48`**
- **Found during:** Task 3 (fIndexOracle reader implementation)
- **Issue:** RESEARCH.md §Pattern 8 decode snippet used `raw[-26:]` (reads zero padding as data). boros_bot_guide.md L206 uses `val >> 48` (discards lower 6-byte zero pad). The two produce different results.
- **Fix:** Implemented `val256 = int.from_bytes(raw, "big"); val208 = val256 >> 48` per bot guide. Confirmed the struct occupies the upper 26 bytes (MSB side) of the 32-byte ABI return. Documented in schema-notes.md.
- **Files modified:** `python/src/boros_brain/data/findex_reader.py`
- **Verification:** `test_findex_decode.py` round-trip tests all pass; decode produces correct field values.
- **Committed in:** `720543c`

**2. [Rule 2 - Missing Critical] Added `insert_clo_snapshot(conn,...)` low-level writer sibling**
- **Found during:** Task 2 (test_markets_poller.py implementation)
- **Issue:** Tests that pre-seed a SQLite fixture need to pass an existing connection; `insert_clo_history(path,...)` always opens its own connection (unsuitable for test transaction lifecycle control).
- **Fix:** Added `insert_clo_snapshot(conn, ...)` as a lower-level sibling that accepts a `sqlite3.Connection`. Both live in `state/writers/clo_history.py`. Single-writer discipline preserved — only `markets_poller.py` imports this module.
- **Files modified:** `python/src/boros_brain/state/writers/clo_history.py`
- **Committed in:** `979e11c`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both necessary for correctness. The bytes32 decode fix is load-bearing — wrong decode would produce garbage fIndex values silently. The writer sibling is needed for testability only; no production behavior change.

## Issues Encountered

- **A5 shape surprise (expected, handled):** The `/markets` response was wrapped `{results:[...]}` rather than a bare list or `{markets:[...]}`. Handled by building Pydantic schema against the real capture before writing poller code — exactly the A5-reconcile-first strategy prescribed by the plan.
- **bytes32 decode discrepancy between RESEARCH.md snippet and boros_bot_guide.md:** RESEARCH.md had the wrong decode direction. boros_bot_guide.md (primary reference) was authoritative; implementation follows bot guide.

## User Setup Required

None — no external service configuration required beyond the existing `RPC_URL_ARBITRUM` env var already established in 01-07.

Operator can run the live-RPC smoke test (skipped on CI) to confirm bytes32 decode against mainnet:
```bash
cd python && CI= uv run pytest tests/test_findex_reader.py::test_findex_decode_from_live_rpc -x -v
```

## Next Phase Readiness

- **01-10 (reward-budget poller):** `make_boros_rest_client` and `insert_*` writer pattern available; poller architecture established.
- **01-11 (SCALE calibration):** `clo_history` will accumulate `(clo_lower_thresh, clo_upper_thresh, f_index_raw)` tuples; SCALE calibration needs two rows ≥1 day apart.
- **01-12 / DATA-09 (economics gate):** `FIndexReader.latest_annualized_rate()` is the live implied APR feed; `MarketsPoller.tick()` is the CLO-change detector.
- **Phase 4 SAFE-02:** `FIndexReader.get_latest_fIndex()['fTime']` vs `chain_time.now_cached()` staleness check is already architected in the reader (non-halting at this layer; Phase 4 applies the `0.7 × maxUpdateDelay` threshold).

---
*Phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate*
*Completed: 2026-04-24*
