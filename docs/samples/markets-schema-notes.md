# Boros /markets Response Schema Notes

**Captured:** 2026-04-24 via `curl https://api.boros.finance/open-api/v1/markets`
**File:** `docs/samples/markets-response.json` (58 KB, 30 markets)

## Top-Level Shape

The response is a **wrapped object** (not a bare list):

```json
{
  "results": [...],
  "total": 30,
  "skip": 0,
  "syncStatus": {
    "blockNumber": 455701106,
    "timestamp": 1776996232
  }
}
```

Key finding: **NOT a bare list** and **NOT `{markets: [...]}` or `{data: [...]}`** — it is `{results: [...]}`.
This supersedes the draft schema in the plan which assumed `{markets: [...]}`.
Pydantic schema uses `MarketsResponse` with a `results: list[Market]` field.

## Market Object Structure

Each market in `results` is a nested object with the following top-level keys:

| Field | Type | Notes |
|-------|------|-------|
| `marketId` | `int` | Integer, not a string like `"ETH-29MAY2026"` — contrary to initial planning assumption |
| `address` | `str` | Contract address (Arbitrum) |
| `tokenId` | `int` | Integer token ID |
| `imData` | `object` | Immutable market data (name, symbol, maturity, tick settings) |
| `config` | `object` | Market config including CLO thresholds, fIndexOracle address, fees |
| `extConfig` | `object` | AMM address, settlement fee rate, payment period, maxUpdateDelay |
| `metadata` | `object` | Human-readable metadata (name, leverage, asset symbol, platform) |
| `data` | `object` | Live data (volume, OI, APRs, best bid/ask, volatility) |
| `state` | `str` | Market state string e.g. `"Normal"` |

## Critical Fields: CLO Thresholds + fIndexOracle

These live **inside `config`**, NOT at the top-level market object:

| Field | Path | Type | Example | Notes |
|-------|------|------|---------|-------|
| `cloLowerThresh` | `config.cloLowerThresh` | `int` | `9300` | Integer in tick-space (NOT float/percent) |
| `cloUpperThresh` | `config.cloUpperThresh` | `int` | `9500` | Integer in tick-space |
| `fIndexOracle` | `config.fIndexOracle` | `str` | `"0x1950dc94..."` | Per-market oracle address |
| `takerFee` | `config.takerFee` | `str` | `"500000000000000"` | 1e18-denominated string (0.05% = 5e14) |

**CLO type correction:** Initial planning assumed `cloLowerThresh: float`. Reality is `int` (tick-space integer). Pydantic accepts `Union[int, float]` or just `float` (int coerces to float) — using `float` in schema for forward-compat.

**fIndexOracle confirmed present on every incentivized market.** Zero address (`0x0000...0000`) appears on `markRateOracle` for some markets — confirmed that `fIndexOracle` is the correct field to use.

## imData Fields

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | Human name e.g. "BINANCE ETHUSDT 29 May 2026" |
| `symbol` | `str` | API symbol e.g. "BINANCE-ETHUSDT-29MAY2026" — useful as human-readable market ID |
| `maturity` | `int` | Unix timestamp |
| `isIsolatedOnly` | `bool` | |
| `tickStep` | `int` | |
| `iTickThresh` | `int` | |
| `marginFloor` | `float` | |

## extConfig Fields (relevant for Phase 4 SAFE-02)

| Field | Type | Notes |
|-------|------|-------|
| `ammAddress` | `str` | AMM contract address |
| `ammId` | `int` | |
| `isPositiveAMM` | `bool` | |
| `settleFeeRate` | `str` | 1e18-denominated string |
| `paymentPeriod` | `int` | Seconds between settlements |
| `maxUpdateDelay` | `int` | Seconds — used by SAFE-02 oracle staleness: `fTime > 0.7 × maxUpdateDelay` |

`maxUpdateDelay = 900` (15 minutes) for most markets.

## data Fields (live market data)

| Field | Type | Notes |
|-------|------|-------|
| `markApr` | `float` | |
| `lastTradedApr` | `float` | |
| `midApr` | `float` | |
| `bestBid` | `float` | |
| `bestAsk` | `float` | |
| `floatingApr` | `float` | Current underlying funding rate |
| `longYieldApr` | `float` | Reward APR for Long side |
| `nextSettlementTime` | `int` | Unix timestamp |
| `timeToMaturity` | `int` | Seconds to maturity |
| `settlementsToMaturity` | `int` | |
| `dailyVolatility` | `float` | |
| `dailyVolatilityState` | `str` | e.g. `"ready"` |
| `volume24h` | `float` | |
| `notionalOI` | `float` | |
| `assetMarkPrice` | `float` | |
| `rateSensitivity` | `float` | |
| `ammImpliedApr` | `float` | |

## config Fields (complete list)

| Field | Type | Notes |
|-------|------|-------|
| `maxOpenOrders` | `int` | |
| `markRateOracle` | `str` | Often zero address |
| `fIndexOracle` | `str` | Per-market oracle — **USE THIS** for DATA-07 |
| `hardOICap` | `str` | 1e18-denominated |
| `takerFee` | `str` | 1e18-denominated: `"500000000000000"` = 0.05% |
| `otcFee` | `str` | 1e18-denominated |
| `liqSettings` | `object` | Liquidation params |
| `kIM` / `kMM` | `str` | Margin params |
| `tThresh` | `int` | Seconds |
| `loUpperConstBase1e4` / `loUpperSlopeBase1e4` | `int` | CLO range formula params |
| `loLowerConstBase1e4` / `loLowerSlopeBase1e4` | `int` | CLO range formula params |
| `maxRateDeviationFactorBase1e4` | `int` | |
| `closingOrderBoundBase1e4` | `int` | |
| `status` | `int` | Market status code |
| `useImpliedAsMarkRate` | `bool` | |
| `softOICap` | `int` | |
| `cloLowerThresh` | `int` | **CLO lower bound (tick-space)** |
| `cloUpperThresh` | `int` | **CLO upper bound (tick-space)** |

## Fields Assumed vs Reality

| Assumed Field | Reality | Decision |
|---------------|---------|----------|
| `marketId: str` (e.g. "ETH-29MAY2026") | `marketId: int` (integer) | Use `imData.symbol` as the string key in DB/poller; store as `market_id` using `imData.symbol` value |
| Response is `{markets: [...]}` | Response is `{results: [...]}` | Schema field renamed to `results` |
| `cloLowerThresh: float` at market top-level | `config.cloLowerThresh: int` (nested) | Access via `m.config.clo_lower_thresh`; cast to float in DB insert |
| `cloUpperThresh: float` at market top-level | `config.cloUpperThresh: int` (nested) | Same |
| `fIndexOracle: str` at market top-level | `config.fIndexOracle: str` (nested) | Access via `m.config.findex_oracle` |
| `tickSize: float` at top-level | Not present at top-level; `imData.tickStep: int` + `config.loUpperConstBase1e4` etc. | Parse tick step from `imData.tickStep` if needed |
| `takerFee: float` (percentage) | `config.takerFee: str` (1e18 string like "500000000000000") | Decode as `int(takerFee) / 1e18` for float |
| `maturity: int` at top-level | `imData.maturity: int` | Access via `m.im_data.maturity` |

## Market ID Strategy

Since `marketId` is an integer (e.g. `74`) and not a human-readable string, the poller uses `imData.symbol` (e.g. `"BINANCE-ETHUSDT-29MAY2026"`) as the string key for `clo_history.market_id`. This matches the PROJECT.md naming convention and the KNOWN_ORACLES dict in `findex_reader.py`.

## Fields Not Anticipated (Discovered)

| Field | Location | Decision |
|-------|----------|----------|
| `syncStatus` | top-level | **parse** — `blockNumber` + `timestamp` useful for freshness check |
| `skip` | top-level | ignore — pagination offset |
| `total` | top-level | parse — count of markets |
| `extConfig.maxUpdateDelay` | per market | **parse** — required for SAFE-02 oracle staleness `fTime > 0.7 × maxUpdateDelay` |
| `data.longYieldApr` | per market | parse in Wave 2 (DATA-09 economics gate) |
| `imData.tickStep` | per market | log-only for now; screener may use in Wave 2 |
| `state` | per market | parse — `"Normal"` vs other values signal market health |

## Validation Against Known Addresses

BINANCE-ETHUSDT-29MAY2026 (marketId=N):
- `config.fIndexOracle = "0x1950dc94e3063267049482f075af72107eb79352"` — **matches RESEARCH.md §Pattern 8**
- `config.cloLowerThresh = 9300`, `config.cloUpperThresh = 9500` — **matches PROJECT.md Context**

BINANCE-ETHUSDT-26JUN2026:
- `config.fIndexOracle = "0x9dd097e8e7b18a79ac86ddac72d0cdf72017198c"` — **matches RESEARCH.md**

BINANCE-ETHUSDT-25SEP2026:
- `config.fIndexOracle = "0x7fe191632c66ddbd14d6fbe1e331744b894a2b7b"` — **matches RESEARCH.md**

## A5 Landmine Status

**CLOSED.** The `/markets` response shape was significantly different from the assumed flat structure. Critical differences:
1. Wrapped in `{results: [...]}` not bare list
2. CLO thresholds nested under `config.*` not top-level
3. `marketId` is an integer; use `imData.symbol` as string identifier
4. `fIndexOracle` is nested under `config.fIndexOracle`

All differences documented and schema built against real response.
