# Boros Limit Order Reward Farming — Research & Build Guide

## What Is Boros

Boros is an on-chain **interest rate swap (IRS) trading platform** built by Pendle, deployed on Arbitrum. It is not a spot or perpetual market — what is being traded is the *rate* itself, specifically funding rates from centralized exchanges (Binance, OKX, Hyperliquid, Bybit) and other yield sources (staking rates, commodities).

### Core Mechanic

Every market on Boros represents a bet on whether a floating rate (e.g. Binance BTC funding rate) will be higher or lower than a fixed rate over a defined period ending at **maturity**.

- **Long YU** — pay a fixed APR, receive the floating underlying APR. Profitable if actual funding > implied APR.
- **Short YU** — receive a fixed APR, pay the floating underlying APR. Profitable if actual funding < implied APR.
- **YU (Yield Unit)** — represents the yield of 1 unit of collateral in the underlying market.

The "price" of any trade is expressed as **Implied APR** — the market's consensus estimate of average future funding rate until maturity.

### Architecture

Boros uses a **hybrid CLOB + AMM** model:

- A full **Central Limit Order Book (CLOB)** with rate-time priority matching (better rate first, FIFO within same rate)
- An **AMM** that acts as a passive liquidity provider alongside resting orders
- 65,536 discrete tick levels per market using exponential rate mapping: `rate = 1.00005^(tick × tickStep) - 1`
- Deployed on **Arbitrum**

### Key Terms

| Term | Meaning |
|---|---|
| Implied APR | The "price" — market's expected average rate until maturity |
| Mark APR | TWAP oracle (5-min window) used for margining and liquidations |
| Underlying APR | Current live rate from the external oracle (e.g. Binance funding) |
| My Fixed APR | Your locked-in rate for your open position |
| Notional Size | Equivalent underlying asset size your YU position earns yield from |
| Net Balance | Collateral + unrealized PnL — must stay above maintenance margin |
| iTickThresh | Per-market tick threshold (max ticks from mark rate for order placement) |
| fIndex | Cumulative funding index — tracks total yield accumulated since pool inception |
| fIndexOracle | Per-market on-chain contract tracking the fIndex |

---

## The Strategy: Passive Limit Order Reward Farming

### What the Incentive Program Is

Boros incentivizes liquidity in specific rate ranges by rewarding accounts that have **resting limit orders within the incentivized range**. Rewards accumulate **time-weighted** — the longer your order sits in the range without being cancelled or purged, the more you earn.

Rewards are distributed off-chain via a **Merkle distributor** (`MultiTokenMerkleDistributor.sol`). The protocol periodically computes how much each address earned and updates a Merkle root on-chain. You claim by submitting a Merkle proof to the contract.

### The Core Thesis

Post limit orders at the **outer edges** of the incentivized rate range — far enough from mid that fill probability is low, but within the range so you qualify for rewards. Capital earns yield simply by sitting there, with no active trading required.

```
Incentivized range: e.g. -1.34% to -0.85% implied APR

  unlikely to fill                      unlikely to fill
  [bid @ -1.34%] -------- mid @ -0.99% -------- [ask @ -0.85%]
        ↑                                               ↑
   earn rewards                                    earn rewards
```

### Why This Is Not Regular Market Making

In a regular market: buy at X, sell at X + spread, pocket the spread immediately.

In Boros: if your order gets filled, you've entered an IRS position. You don't pocket a spread — you're now obligated to pay or receive the difference between your fixed rate and the floating rate **until maturity**. The P&L accrues continuously and depends entirely on what funding rates do between now and pool expiry.

This is why **fills are bad** for this strategy. They expose you to IRS risk you don't want. The goal is to earn rewards while having orders sit unfilled.

---

## Platform Technical Reference

### REST API

Base URL: `https://api.boros.finance/open-api/v1/`

Key endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /markets` | All markets — config, pricing, CLO ranges, oracle addresses |
| `GET /markets/order-books` | Live order book per market |
| `GET /markets/market-trades` | Recent trades |
| `GET /accounts/limit-orders` | Your open orders |
| `GET /accounts/active-positions` | Your open IRS positions |
| `GET /accounts/gas-balance` | Gas balance for Send Txs Bot |
| `GET /v2/accounts/all-limit-orders` | All open orders (v2) |
| `POST /calldata/place-orders` | Generate calldata to place orders |
| `POST /calldata/place-orders-with-rate` | Place orders by APR rather than tick |
| `POST /calldata/cancel-order` | Generate calldata to cancel an order |
| `GET /simulations/place-order` | Simulate an order before submitting |
| `GET /charts/ohlcv` | OHLCV candle data |

Interactive docs: `https://api.boros.finance/open-api/docs`

### Order Placement Architecture (Send Txs Bot)

Boros uses a **dual-wallet model**:

- **Root wallet** — signs deposits, withdrawals, approvals. Never exposed to hot trading logic.
- **Agent wallet** — signs trading transactions (place/cancel orders). Routed through the Send Txs Bot which submits on-chain and charges gas from your gas balance.

SDK: `npm install @pendle/sdk-boros`

Send Txs Bot base: `https://api.boros.finance/send-txs-bot/v2/`

### Order Types Supported

- `GTC` — Good Till Cancel (standard resting order)
- `IOC` — Immediate Or Cancel
- `FOK` — Fill Or Kill
- `ALO` — Add Liquidity Only (maker-only, will not take)
- `SOFT_ALO` — Soft Add Liquidity Only

Use **GTC** or **ALO** for the reward farming strategy.

### Order Constraints

- Max 80–100 open orders per account (market-specific, check `maxOpenOrders` in market config)
- No minimum order size, but must be non-zero
- Self-trade prevention — you cannot fill your own orders
- Maker orders must stay within computed bounds or get purged: `Upper Bound = Mark Rate × (1 + loUpperConst + loUpperSlope × TimeToMaturity)`
- Taker rate deviation limited by `maxRateDeviationFactorBase1e4`

### Fees

- **Makers: zero fees** on position opening
- **Takers: 0.05%** on position opening
- **Settlement fee**: charged every payment period (8h for Binance markets)
- **Market entrance fee**: charged on entry

This means your resting limit orders cost nothing to place, and if filled you pay as a maker (zero) — but you now hold an unwanted IRS position.

### WebSocket

Real-time feeds available for order book updates and account state. Use for fill detection and purge detection.

---

## Identifying Incentivized Ranges

### From the API

The `GET /markets` response contains per-market:

```json
{
  "imData": {
    "iTickThresh": 583
  },
  "config": {
    "cloLowerThresh": 9300,
    "cloUpperThresh": 9500
  }
}
```

- `cloLowerThresh` / `cloUpperThresh`: define the incentivized range in internal fIndex display units. Zero means no active incentive range for that market.
- `iTickThresh`: tick distance parameter (separate from CLO range).

Markets where `cloLowerThresh == 0` have no active incentive range. Skip them.

### Converting CLO Values to APR

CLO threshold values are in fIndex display units. Conversion requires the current fIndex value from the market's oracle.

**Formula:**
```
APR = (cloThresh - fIndex_display) / timeToMaturity_years / S
```

Where:
- `fIndex_display = 10000 + floatingIndex_raw / SCALE`
- `floatingIndex_raw` = from `fIndexOracle.getLatestFIndex().floatingIndex` (int112, 1e18 precision)
- `SCALE` ≈ 5.591e12 (calibrated, may vary per market — verify per market type)
- `S` ≈ 402,648 (calibrated for ETH Binance markets — verify per market type)
- `timeToMaturity_years` = from API `timeToMaturity` field (seconds) / 31,536,000

**One-time calibration per market:**
1. Read website-displayed APR range for a market
2. Read `cloLowerThresh`, `cloUpperThresh` from API
3. Call `fIndexOracle.getLatestFIndex()` on-chain to get `floatingIndex_raw`
4. Solve for SCALE and S using two-equation system

### fIndex Oracle

Each market has a unique `fIndexOracle` address (in the market's `config.fIndexOracle` field).

```
Interface: IFIndexOracle
Key functions:
  getLatestFIndex() → returns FIndex (packed bytes26)
    └── .floatingIndex() → int112 (accumulated in 1e18 precision)
    └── .feeIndex() → uint64
    └── .fTime() → uint32 (timestamp of last update)
  
  latestAnnualizedRate() → int256 (current spot funding rate, 1e18 precision)
```

**Decoding `getLatestFIndex()` response (bytes26 packed into bytes32):**
```python
raw_hex = "..."  # 64-char hex from eth_call
val = int(raw_hex, 16)
val208 = val >> 48  # shift right 48 bits (6 bytes padding)

fTime           = (val208 >> 176) & 0xFFFFFFFF
floatingIndex   = (val208 >> 64) & ((1 << 112) - 1)
if floatingIndex >= (1 << 111):
    floatingIndex -= (1 << 112)  # sign extend
feeIndex        = val208 & ((1 << 64) - 1)
```

**Function selectors (confirmed):**
- `getLatestFIndex()`: `0xbd63342e`
- `latestAnnualizedRate()`: `0x972b365a`

**RPC:** Arbitrum One — `https://arb1.arbitrum.io/rpc`

### Converting APR to Ticks

```python
import math

def apr_to_tick(apr, tick_step):
    return math.log(1 + apr) / (tick_step * math.log(1.00005))

# Example: Binance ETHUSDT, tickStep=2
# -1.34% APR → tick -135
# -0.85% APR → tick -85
```

Ticks must be integers. Round toward mid (less aggressive) for lower fill risk.

---

## Known Markets (as of April 2026)

Active markets span Hyperliquid, Binance, OKX, Bybit, Lighter across:
- BTC, ETH, SOL, XRP, HYPE
- Gold (XAU), Silver (XAG), Crude Oil (CL), Brent Oil
- S&P 500, XYZ100

Maturities: April 24 2026, May 21 2026, May 29 2026, June 26 2026, September 25 2026

ETH Binance markets share `cloLower=9300, cloUpper=9500`. BTC Binance markets use `cloLower=309.69, cloUpper=316.35`. Markets with `clo=0` are not incentivized.

---

## Risk Framework

### Risk 1: Fills (Primary)

**Scenario:** Mark APR drifts toward your resting order and a taker sweeps it.

**Impact:** You're now holding an IRS position. If the rate moves further in that direction, your net balance deteriorates. If it breaches maintenance margin, liquidation occurs.

**Mitigation:**
- Post at the very outer edge of the incentivized range (furthest from mid)
- Monitor `latestAnnualizedRate` — if it's moving rapidly toward one side, temporarily cancel that order
- If filled: close immediately with a market order. Accept the taker fee as insurance cost.
- Never hold a fill hoping for mean-reversion. That's a different strategy.

### Risk 2: Order Purging

**Scenario:** Mark rate moves enough that your resting order falls outside the protocol's allowed bounds. The protocol force-cancels it with `PURGED` status.

**Impact:** Time-weight accumulation resets. You must repost to resume earning.

**Formula for upper bound:**
```
Upper Bound = Mark Rate × (1 + loUpperConst + loUpperSlope × TimeToMaturity)
```

`loUpperConst` and `loUpperSlope` are in the market config (e.g. `loUpperConstBase1e4=40` means 0.4%).

**Mitigation:**
- Monitor order status via WebSocket
- Repost immediately on purge detection
- Consider posting slightly inside the CLO boundary (not exactly at the edge) to create a buffer before purge risk

### Risk 3: Maturity Decay

**Scenario:** As pool approaches maturity, allowed order bounds tighten (`loUpperSlope × TimeToMaturity` shrinks). Orders that were safe become purgeable.

**Impact:** Increasing purge frequency near expiry. Rewards also diminish as there are fewer settlements left.

**Mitigation:**
- Track days-to-maturity. Consider exiting positions and moving to a later-maturity pool when within 2 weeks of expiry.
- Monitor `marginFloor` — as maturity approaches this becomes binding.

### Risk 4: Collateral Opportunity Cost

**Scenario:** Capital posted as margin earns rewards but is locked. Alternative yield exists elsewhere.

**Impact:** If reward APR on posted collateral is lower than alternatives, the strategy isn't capital-efficient.

**Mitigation:**
- Quantify this before deploying. Know what the reward rate is in APR terms on your posted collateral.
- Use isolated margin, not cross-margin, to contain exposure.

### Risk 5: Range Shift (CLO Update)

**Scenario:** Protocol updates `cloLowerThresh`/`cloUpperThresh`. Your orders are now outside the new incentivized range.

**Impact:** You stop earning rewards but capital remains posted and at risk of fills in the new rate environment.

**Mitigation:**
- Poll `GET /markets` every few minutes. Detect changes in clo values immediately.
- On detection: cancel existing orders, recalibrate, repost in new range.
- Alert system required — a range shift while the bot is offline is dangerous.

### Risk 6: Smart Contract / Keeper Risk

**Scenario:** The fIndex oracle keeper fails to update. `maxUpdateDelay` is exceeded.

**Impact:** Mark rate becomes stale. Your orders may be priced against incorrect data.

**Mitigation:**
- Monitor `fTime` from the oracle. If `now - fTime > maxUpdateDelay`, pause order activity.
- This should be a hard circuit breaker in the bot.

---

## What Must Be Answered Before Going Live

### Non-negotiable — answer these first

1. **Reward token and emission rate**
   - What token are rewards paid in?
   - What is the total emission per market per day/week?
   - Is it pro-rata by order size, time-weighted, or both?
   - Is there a per-account cap?
   - Source: Pendle Discord / whitepaper / team directly

2. **Qualifying conditions**
   - Minimum order size to earn rewards?
   - Must both bid and ask be posted, or is one side sufficient?
   - Minimum posting duration per epoch?
   - Source: whitepaper or team

3. **Claim mechanics**
   - How frequently is the Merkle root updated?
   - What is the gas cost to claim on Arbitrum?
   - Is there a minimum claimable amount?

4. **Historical fill rate at the edges**
   - Using Boros NDJSON historical data: how often do orders at the outer CLO boundary get filled?
   - What is the subsequent rate path after fills at that level?
   - This is the core backtest question.

5. **Reward APR on posted collateral**
   - Take known emission rate, divide by total notional currently posted in the incentivized range.
   - Compare to: fill risk cost, gas cost, alternative yield.

### Secondary — answer before scaling

6. How does the reward share change as more capital enters the range (dilution effect)?
7. Are other bots currently farming the same ranges?
8. What is SCALE and S for non-ETH markets (BTC, SOL, etc.)?
9. Does SCALE change when cloLower/cloUpper is updated by governance?

---

## Backtest Requirements

Before any live capital, the backtest must confirm:

### Data Sources

| Data | Source |
|---|---|
| Boros trades, OHLCV, order book snapshots | `https://historical-data.boros.finance` (monthly NDJSON) |
| Binance funding rate history | Binance public API (`GET /fapi/v1/fundingRate`) |
| OKX funding rate history | OKX public API |
| Hyperliquid funding rate history | Hyperliquid public API |

### What the Backtest Must Measure

1. **Fill frequency**: How many times per week would an order at the CLO boundary have been filled?
2. **Fill severity**: When filled, what is the average P&L impact before the rate reverts?
3. **Time-weight accumulation**: What fraction of time are orders in the valid range without being purged?
4. **Purge frequency**: How often do mark rate movements push orders outside bounds?
5. **Break-even reward rate**: What reward rate (in APR on collateral) makes the strategy net-positive after fill losses and gas?

### Simulation Logic

```
for each 8-hour epoch in historical data:
    current_rate = historical_funding_rate[epoch]
    mid_apr = historical_mid_apr[epoch]  # from Boros NDJSON
    
    bid_at = cloLower_apr
    ask_at = cloUpper_apr
    
    # Check for fill
    if epoch_low_apr <= bid_at:
        fill_occurred(side='long', rate=bid_at)
        close_position(next_epoch_rate)
        pnl_from_fill = calculate_irs_loss(entry=bid_at, exit=next_epoch_rate, duration)
    
    if epoch_high_apr >= ask_at:
        fill_occurred(side='short', rate=ask_at)
        close_position(next_epoch_rate)
        pnl_from_fill = calculate_irs_loss(entry=ask_at, exit=next_epoch_rate, duration)
    
    # Check for purge
    if order_outside_mark_rate_bounds(mark_apr[epoch]):
        purge_occurred()
        time_weight_accumulation = reset()
    
    # Accumulate rewards if in range
    if in_incentivized_range and not purged:
        rewards += reward_rate_per_epoch * order_size

net_result = total_rewards - total_fill_losses - total_gas_cost
```

---

## Bot Architecture (When Ready to Build)

```
┌─────────────────────────────────────────────────────────┐
│                    CONFIG LAYER                          │
│  Target markets, CLO calibration (SCALE, S per market)  │
│  Max order size, circuit breaker thresholds             │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  MARKET DATA LOOP (every ~30s)           │
│  GET /markets → detect cloLower/cloUpper changes        │
│  eth_call latestAnnualizedRate() → spot funding rate    │
│  eth_call getLatestFIndex() → fIndex_display            │
│  Compute current APR bounds from CLO formula            │
│  Convert APR bounds → ticks                             │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  ORDER MANAGER                           │
│  GET /accounts/limit-orders → current order state       │
│  If order missing/purged → repost at CLO edge ticks     │
│  If CLO range changed → cancel all, recalibrate, repost │
│  If rate velocity too high → cancel at-risk side        │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              WEBSOCKET FILL MONITOR                      │
│  Subscribe to order fills and account updates           │
│  On fill: immediately generate close calldata           │
│  Route through Send Txs Bot to execute on-chain         │
│  Log fill, calculate loss, repost limit order           │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  CIRCUIT BREAKERS                        │
│  fIndex oracle stale (fTime > maxUpdateDelay) → pause   │
│  Rate moved > X% in 1 epoch → cancel at-risk side      │
│  Net balance below threshold → emergency close all      │
│  CLO = 0 (range removed) → cancel all, alert           │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  CLAIM SCHEDULER                         │
│  Check Merkle root update events on-chain               │
│  On new root: call claim() with Merkle proof            │
│  Log claimed amount and token                           │
└─────────────────────────────────────────────────────────┘
```

### Execution

- All order transactions go through `POST /send-txs-bot/v2/` with agent wallet signatures
- Agent wallet is a hot wallet with limited permissions (trading only)
- Root wallet stays cold — only needed for deposits/withdrawals
- Gas balance must be maintained in the Send Txs Bot system

---

## Key Contracts (Arbitrum)

| Contract | Address |
|---|---|
| MultiTokenMerkleDistributor | (check deployments repo) |
| fIndexOracle (Binance ETHUSDT 29 May 2026) | `0x1950dc94e3063267049482f075af72107eb79352` |
| fIndexOracle (Binance ETHUSDT 26 Jun 2026) | `0x9dd097e8e7b18a79ac86ddac72d0cdf72017198c` |
| fIndexOracle (Binance ETHUSDT 25 Sep 2026) | `0x7fe191632c66ddbd14d6fbe1e331744b894a2b7b` |
| fIndexOracle (Binance BTCUSDT 29 May 2026) | (from markets API) |

Full deployed addresses: `https://github.com/pendle-finance/boros-core-public/tree/main/deployments`

---

## Calibration Reference (Binance ETHUSDT 29 May 2026, calibrated Apr 22 2026)

| Parameter | Value |
|---|---|
| cloLower | 9300 |
| cloUpper | 9500 |
| Incentivized range (APR) | -1.34% to -0.85% |
| Bid tick | -135 |
| Ask tick | -85 |
| tickStep | 2 |
| fIndex_display at calibration | 9846.94 |
| floatingIndex_raw at calibration | -855,750,000,000,000 |
| SCALE | 5,591,244,281,197 |
| S (APR formula constant) | 402,648 |
| latestAnnualizedRate at calibration | -2.33% APR |
| markApr at calibration | -0.99% APR |
| APR bound drift per epoch | ~0.009% |

**Note:** SCALE and S require re-calibration for each unique market. The values above apply to Binance ETHUSDT 29 May 2026 only.

---

## Open Questions (Answers Needed Before Live)

- [ ] What token are CLO rewards paid in?
- [ ] What is the emission rate per market per epoch?
- [ ] Is the reward split pro-rata by order size, or equally among all qualifying accounts?
- [ ] Minimum order size to qualify for rewards?
- [ ] Must both sides (bid + ask) be posted, or does one side qualify independently?
- [ ] How frequently is the Merkle root updated?
- [ ] What determines when cloLower/cloUpper are updated, and by how much notice?
- [ ] What is SCALE and S for BTC, SOL, and other markets?
- [ ] Does SCALE remain stable over the life of a pool?
- [ ] Historical fill rate at CLO boundary ticks (requires backtest on NDJSON data)
- [ ] Is there currently competing bot activity in the incentivized ranges?

---

## Resources

| Resource | URL |
|---|---|
| Boros user docs | `https://docs.pendle.finance/boros-docs/Introduction` |
| Boros dev docs | `https://docs.pendle.finance/boros-dev` |
| REST API docs | `https://api.boros.finance/open-api/docs` |
| SDK | `npm install @pendle/sdk-boros` |
| Core contracts repo | `https://github.com/pendle-finance/boros-core-public` |
| Deployed addresses | `https://github.com/pendle-finance/boros-core-public/tree/main/deployments` |
| Historical data | `https://historical-data.boros.finance` |
| Pendle Discord | `https://discord.com/invite/EAujvncY2R` |
