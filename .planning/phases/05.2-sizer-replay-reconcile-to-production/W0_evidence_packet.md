# Phase 05.2 — W0 Evidence Packet

**Collected:** 2026-04-30T02:32–05:21 UTC
**Operator:** macbookair
**Status:** Current
**Note:** E1 probe used sizes 0.3, 0.5, 1 YU across all BTC and ETH markets. Binding market ETH screenshots include funded-account panels (t+150). E1 margin_per_yu_usd for non-binding markets pending next session (screenshots captured, context exhausted before extraction).

## ⚠ CRITICAL FINDING — Epoch flip on long/short split

Between the prior session (used to derive CONTEXT.md Bug #2) and this probe, the long/short reward split **reversed**:

| epoch | long PENDLE/day | short PENDLE/day | long_side_split |
|-------|-----------------|------------------|-----------------|
| prior (CONTEXT.md source) | 14.5 | 29.78 | 0.327 |
| current (this probe, T0 02:32) | 34.17 | 10.11 | **0.771** |
| current (T+150, 05:19) | 33.67 | 10.62 | **0.760** |

Total budget unchanged: ~44.28 PENDLE/day. Only the split changed.

**Implication for Plan 04 (Bug #2 data correction):** The planned insert of `long_side_split=0.327` was correct for the prior epoch but is wrong for the current epoch (split is now ~0.76). Plan 04 must use the current epoch's split. The `effective_at_utc` column added in Plan 03 (W2a schema) allows storing epoch-keyed rows — both the prior-epoch row (0.327, effective prior Friday) and the current-epoch row (0.760, effective this Friday) should be inserted.

**Implication for E2 / ship-gate prediction:** The long APR badge at T0 was 389% and T+150 was 296% (vs prior session 489%). The lower long APR in the current epoch reflects the flipped split (long pool grew, diluting per-dollar rewards).

Also: **Incentivized range has shifted** from prior 0.74–1.26% to 0.52–1.17% (T0) / 0.54–1.17% (T+150). Edge placements in strategy YAMLs will need updating.

## E1 — Cross-market trial-order probe

### Market: BINANCE-ETHUSDT-25SEP2026 (binding, from CONTEXT.md prior session, slider=0%)

| side | size_yu | implied_apr_pct | rate_sensitivity_eth | margin_required_eth | while_active_pendle_per_day | when_filled_pendle |
|------|---------|-----------------|----------------------|---------------------|-----------------------------|--------------------|
| long | 0.1 | 0.90 | 0.000405 | 0.000811 | 0.02 | 0.05 |
| long | 0.45 | 0.90 | 0.00182 | (off-screen) | 0.08 | — |
| short | 0.1 | 0.90 | 0.000405 | 0.000811 | 0.01 | — |
| short | 0.45 | 0.90 | 0.00182 | (off-screen) | 0.04 | — |

Derived (prior session, slider=0%):
- margin_per_yu_usd: **18.30** (= 0.000811 ETH × $2258/ETH / 0.1 YU)
- rate_sensitivity_per_yu_usd_per_pct: 9.13 (= 0.000405 ETH × $2258)

Current session (t+150, funded, slider=100% = minimum margin):
- 1 YU short: rate_sensitivity=0.00405 ETH/1%, margin=0.00181383 ETH → margin_per_yu=$4.08/YU
- 1 YU long: rate_sensitivity=0.00405 ETH/1%, margin=0.00181383 ETH → margin_per_yu=$4.08/YU
- 0.5 YU long: slider=73%, liq APR=-0.45%, rewards: 0.02 filled / 0.06 active/day
- 0.3 YU long: slider=44%, liq APR=-2.27%, rewards: 0.01 filled / 0.04 active/day
- 0.3 YU short: slider=44%, liq APR=4.96%, rewards: 0.01 filled / 0.04 active/day
- 0.5 YU short: slider=73%, liq APR=2.34%, rewards: 0.02 filled / 0.02 active/day

NOTE: Slider semantics — slider=100% appears to be minimum margin (most leveraged). Slider=0% = maximum margin. Strategy should use slider=100% for maximum reward efficiency. Prior session labeled slider=0% as "minimum margin" which appears to be incorrect; $18.30/YU was the MAXIMUM margin, slider=100% gives ~$4.08/YU.

### Other markets (E1 — screenshots captured, extraction pending next session)

E1 data for BINANCE-ETHUSDT-29MAY2026, BINANCE-ETHUSDT-26JUN2026, HYPERLIQUID markets, and all BTC markets captured in `/Users/macbookair/Desktop/boros dapp UI/` subdirectories. margin_per_yu_usd extraction deferred to next session due to context limits.

Preliminary: all markets used sizes 0.3, 0.5, 1 YU across long and short.

## E2 — Daily Volatility (binding market)

daily_volatility_pct: **0.34**

Source: orderbook header, BINANCE-ETHUSDT-25SEP2026, confirmed stable across T0 (02:32 UTC) and T+150 (05:19 UTC).

## E3 — Time-stability check (binding market reward statistics)

Reading 1 (T0):
- timestamp_utc: 2026-04-30T02:32:42Z
- long_pendle_per_day: 34.17
- short_pendle_per_day: 10.11

Reading 2 (T0 + 150 min):
- timestamp_utc: 2026-04-30T05:18:54Z
- long_pendle_per_day: 33.67
- short_pendle_per_day: 10.62

Drift:
- e3_drift_pct_long: 1.46% (= 100 × |33.67 - 34.17| / 34.17)
- e3_drift_pct_short: 5.04% (= 100 × |10.62 - 10.11| / 10.11)
- e3_recommended_cadence: **weekly_with_alert** (long <5% → weekly; short just over 5% → alert trigger)

Note: T+150 is 2.5h, not the planned 6-12h. Short drift of 5% over 2.5h implies short rewards may be more volatile; a true 6-12h reading is recommended to confirm cadence.

## E5 — Pendle docs URL (bonus)

e5_url: NOT_FOUND (not checked in this session due to context limits)

If found, quote the LO Liquidity Reward formula here:
> <quote>

## E4 — n_fills=0 audit (Claude-populated, see Task 2)

See `var/reports/n_fills_audit_verdict.json` and `[[n-fills-zero-binding-window-audit]]` wiki page.

Summary:
- n_crossings_lo (0.74%): 6
- n_crossings_hi (1.26%): 9
- max_apr_pct: 2.2039
- min_apr_pct: 0.3908
- mean_apr_pct: 1.4101
- verdict_label: sim_bug_under_counting

**Implication for Wave 4:** n_fills=0 is a simulator bug (APR crosses edges 15 times in 26 days). Wave 4 must NOT assume n_fills=0 is a valid real-market outcome — the 1 Hz tick synthesis plan should be paired with proper fill detection scope verification.
