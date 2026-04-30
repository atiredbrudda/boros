# Phase 05.2 — W0 Evidence Packet

**Collected:** 2026-04-30T02:32–05:21 UTC (T0 + T+150) plus prior-session calculator data
**Operator:** macbookair
**Status:** Current
**Note:** E1 probe used sizes 0.3, 0.5, 1 YU across all BTC and ETH markets. Three reading sets total: prior session (UNFUNDED), T (UNFUNDED at 02:07–02:58 UTC), T+150 (only ETH FUNDED with 0.00556 ETH ≈ $14 at 05:00–05:35 UTC; BTC unfunded throughout). A fourth reading at T+6h is pending to close the 6–12h E3 cadence question.

## Funding-state classification (drives data trust)

| reading | ETH markets (BINANCE + HYPERLIQUID, both venues) | BTC markets | margin readings trustworthy as strategy primitives? |
|---|---|---|---|
| prior session | unfunded | unfunded | **No** — calculator output, not constraint-bound |
| T (02:07–02:58 UTC) | unfunded | unfunded | **No** — calculator output |
| T+150 (05:00–05:35 UTC) | **funded $14** (single ETH deposit funds *all* ETH markets — both BINANCE and HYPERLIQUID venues simultaneously, since funding is per-denomination not per-market) | unfunded (no BTC deposit) | **ETH (both venues): yes**; BTC: tag `unfunded_estimate` |
| T+6h (~08:32 UTC) | **funded $14** (same ETH deposit) | unfunded | **ETH (both venues): yes** |

All "calculator-only" margin readings still reflect the dapp's protocol formula, but the slider auto-positions differently with vs. without real collateral, so cross-session comparison of slider % is invalid. Per-YU margin and rate_sensitivity values *are* invariant to slider position and remain comparable.

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

## E1 — Cross-market trial-order probe (T+150 funded ETH — AUTHORITATIVE)

ETH price assumed = $2547 (cross-check from another reference if precise USD conversion matters). All readings below from T+150 funded ETH ($14 collateral). Slider position is *derived* (auto-set by dapp from margin/free-collateral ratio at fixed liquidation policy), not chosen — same YU input gives different slider % across markets because per-market margin differs.

### Per-panel raw readings

#### BINANCE-ETHUSDT-29MAY2026 (28 days, implied APR -0.89%, Daily Vol ±1.35%)

| screenshot | side | size_yu | slider% | rate_sens (ETH/1%) | margin (ETH) | liq_apr (%) | when_filled | while_active/day |
|---|---|---|---|---|---|---|---|---|
| 5.14.27 | short | 0.3 | 13 | 0.000238 | 0.000715 | 18.24 | <0.01 P | 0 P |
| 5.14.40 | short | 0.5 | 21 | 0.000397 | 0.001192 | 10.85 | <0.01 P | 0.14 P |
| 5.14.53 | short | 1.0 | 43 | 0.000795 | 0.002385 | 4.72 | 0.01 P | 0.27 P |
| 5.15.31 | long | 0.3 | 13 | 0.000238 | 0.000715 | -10.72 | <0.01 P | 0.02 P |
| 5.15.19 | long | 0.5 | 21 | 0.000397 | 0.001192 | -12.13 | <0.01 P | 0.03 P |
| 5.15.07 | long | 1.0 | 43 | 0.000795 | 0.002385 | -6.43 | 0.01 P | 0 P |

#### BINANCE-ETHUSDT-26JUN2026 (56 days, implied APR 0.37%, Daily Vol ±0.47%)

| screenshot | side | size_yu | slider% | rate_sens (ETH/1%) | margin (ETH) | liq_apr (%) | when_filled | while_active/day |
|---|---|---|---|---|---|---|---|---|
| 5.18.17 | short | 0.3 | 13 | 0.000468 | 0.000704 | 9.98 | <0.01 P | 0.03 P |
| 5.18.03 | short | 0.5 | 21 | 0.000781 | 0.001173 | 6.11 | <0.01 P | 0.05 P |
| 5.17.49 | short | 1.0 | 42 | 0.001560 | 0.002347 | 2.93 | 0.01 P | 0.09 P |
| 5.17.05 | long | 0.3 | 13 | 0.000488 | 0.000704 | -9.34 | <0.01 P | 0 P |
| 5.17.17 | long | 0.5 | 21 | 0.000781 | 0.001173 | -5.47 | <0.01 P | 0.05 P |
| 5.17.37 | long | 1.0 | 42 | 0.001560 | 0.002344 | -2.15 | 0.01 P | 0 P |

#### BINANCE-ETHUSDT-25SEP2026 (147 days, BINDING, implied APR 0.90%, Daily Vol ±0.34%)

| screenshot | side | size_yu | slider% | rate_sens (ETH/1%) | margin (ETH) | liq_apr (%) | when_filled | while_active/day |
|---|---|---|---|---|---|---|---|---|
| 5.20.27 | short | 0.3 | 44 | 0.001220 | 0.002432 | 4.96 | 0.027 ETH ($0.06) | 0.01 P |
| 5.20.40 | short | 0.5 | 73 | 0.002030 | 0.004058 | 2.34 | 0.027 ETH ($0.06) | 0.02 P |
| 5.20.53 | short | 1.0 | 100 | 0.004050 | 0.008115 | NA (insuf) | 0 ETH | 0.05 P |
| 5.20.05 | long | 0.3 | 44 | 0.001220 | 0.002432 | -2.27 | 0.01 P | 0.04 P |
| 5.21.19 | long | 0.5 | 73 | 0.002030 | 0.004058 | -0.45 | 0 P | 0.02 P |
| 5.21.04 | long | 1.0 | 100 | 0.004050 | 0.008115 | NA (insuf) | 0.05 P | 0.12 P |

Note: 0.3 YU sept25 margin reads `0.0024315 ETH` (two zeros after decimal, not three — operator-confirmed 2026-04-30). Linear scaling holds across all sizes; my earlier pixel-read with three leading zeros was wrong. The table values above (`0.002432`) are the corrected readings.

### Derived per-market primitives

| market | margin_per_yu_eth (ETH/YU) | margin_per_yu_usd (at $2547 ETH) | rate_sens_per_yu_eth (ETH/1%/YU) |
|---|---|---|---|
| BINANCE-ETHUSDT-29MAY2026 (28d) | 0.00238 | **$6.06** | 0.000795 |
| BINANCE-ETHUSDT-26JUN2026 (56d) | 0.00234 | **$5.96** | 0.001560 |
| BINANCE-ETHUSDT-25SEP2026 (147d) | 0.00811 | **$20.66** | 0.004050 |

Margin per YU is **constant within a market** across all observed sizes (linear scaling on every market, 18 funded ETH data points). Margin per YU does **not** scale linearly with maturity (147d/28d = 3.41× ratio vs duration ratio 5.25×) — the dapp's margin formula factors in market-specific volatility and liquidity beyond pure DV01. Rate sensitivity *does* scale linearly with maturity (correct DV01 behavior).

### q_max sanity-check at $100 collateral, safety_margin=0.9

| market | q_max (YU) |
|---|---|
| may29 (28d) | $100 × 0.9 / $6.06 = **14.85 YU** |
| jun26 (56d) | $100 × 0.9 / $5.96 = **15.10 YU** |
| sept25 (147d, binding) | $100 × 0.9 / $20.66 = **4.36 YU** |

Original CONTEXT.md prediction `q_max ≈ 4.92 YU` for binding market is structurally intact (off only by ETH price drift $2258 → $2547). The "~415% USD-APR" prediction stands.

### Cross-session reconciliation — apparent $18.30 vs $4.08 contradiction RESOLVED

The earlier "different margin/YU between sessions" finding was a **packet transcription error**, not a real session-state difference:

| claim | margin reading recorded in packet | margin reading in screenshot | margin/YU |
|---|---|---|---|
| prior session 0.1 YU long | 0.000811 ETH | (calculator output, no screenshot to re-check) | 0.00811 ETH/YU |
| current session 1 YU short | 0.00181383 ETH (line 53, ~~old~~) | **0.00811513 ETH** (screenshot 5.20.53) | 0.00811 ETH/YU |

**Both sessions agree**: binding-market margin/YU = 0.00811 ETH/YU. USD differs only by ETH price ($18.30 at $2258 → $20.66 at $2547). The "$4.08/YU at slider=100%" claim was based on a misread of `0.008115` as `0.001813` and is **WITHDRAWN**.

### Slider semantics — corrected understanding

The slider is **not a leverage knob** the operator chooses. It is a *visual readout* of "fraction of available collateral consumed by this position at the dapp's current liquidation policy." Same YU input shows different slider % across markets because each market's per-YU margin differs. The strategy primitive is `margin_per_yu_eth` (per market, constant in YU); slider position is a derived display field, not an input.

The earlier packet claim "slider=100% = min margin, slider=0% = max margin" is **WITHDRAWN**.

### HYPERLIQUID ETH markets (T+150 — FUNDED, AUTHORITATIVE — extraction pending)

The single 0.00556 ETH deposit funds *all* ETH markets across both venues (Boros funding is per-denomination, not per-market). HYPERLIQUID-ETH-{29MAY,26JUN,25SEP}2026 T+150 panels are therefore **funded and authoritative**, same trust tier as the BINANCE-ETH panels above. Pixel extraction of the 18 additional data points (3 markets × 3 sizes × 2 sides) is deferred — recommend running it before any Wave 5 multi-market verdict.

Screenshots: `/Users/macbookair/Desktop/boros dapp UI/hyperliquid eth {may 29,jun26,sept25}/t + 150 mins/`.

### BTC markets (UNFUNDED across all readings — `unfunded_estimate`)

Screenshots captured for BINANCE-BTC-{29MAY,26JUN}2026 and HYPERLIQUID-BTC-{29MAY,26JUN}2026 at both T and T+150, but no BTC denomination was deposited at any point — all BTC readings are dapp-calculator output, not constraint-bound. Tagged `unfunded_estimate`. Useful for cross-market comparison and Phase-6 multi-market YAML completeness, **not authoritative for any q_max or ship-gate calculation**. Extraction deferred until needed by Phase 6.

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

Reading 3 (T0 + ~6h, ~08:32 UTC):
- timestamp_utc: 2026-04-30T08:32:00Z (approx)
- long_pendle_per_day: 31.35
- short_pendle_per_day: 12.94
- long_side_split: 0.708 (= 31.35 / 44.29)

Drift (T0 → T+6h):
- e3_drift_pct_long: 8.25% (= 100 × |31.35 - 34.17| / 34.17)
- e3_drift_pct_short: 27.99% (= 100 × |12.94 - 10.11| / 10.11)
- e3_drift_pct_long_split: 8.4% (= 100 × |0.708 - 0.771| / 0.771)
- e3_recommended_cadence: **every_2_to_3_days** (long >5% in 6h → weekly insufficient; short >20% → recalibrate before any epoch boundary)

Note: T+150 drift was 1.46% long / 5.04% short. By T+6h the long split had drifted 8.25% from T0, confirming short rewards are volatile within-epoch. The original `weekly_with_alert` cadence is WITHDRAWN — use `every_2_to_3_days` with an alert if either side drifts >10% intra-check. Current-epoch insert uses T+6h value (0.708) as the most recent authoritative reading.

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

## E6 — Maturity-decay analysis & binding-market justification (Claude-populated)

See `var/reports/oi_vs_maturity_verdict.json`, `var/audit/oi_vs_maturity.png`, `scripts/audit_oi_vs_maturity.py`, and `[[fill-risk-vs-yield-by-maturity]]` wiki page.

### Question this resolved

Phase 05.1 chose `BINANCE-ETHUSDT-25SEP2026` as the binding market on the a-priori reasoning *"longest duration → most reward-budget per epoch → best APR candidate."* Today's dapp probe contradicts that: 28d markets receive 4× the reward budget of 56d/147d markets (Pendle pays for front-month liquidity). The natural follow-on question — *"should we switch to may29 (28d, 4× budget) as binding?"* — required two pieces of evidence the original reasoning lacked: (a) does sept25's budget *grow* over its lifetime as it ages into front-month status, and (b) is sept25's safety advantage real or just a snapshot artifact?

### What the OI proxy query showed

Pendle does not publish reward-budget history (verified: archive has no budget kind; local SQLite has only synthetic placeholders; the live `/markets` API doesn't expose budget fields). Closest proxy: `notionalOI` time-series from the `market-data` archive kind. Hypothesis: if reward allocation correlates with where the activity is, OI growth toward expiry implies budget growth toward expiry.

Result (full output in `oi_vs_maturity_verdict.json`):

| BINANCE ETHUSDT | maturity bucket | OI growth (ETH/day) | level (last reading) |
|---|---|---|---|
| 29MAY2026 | 28d | **148.97** | 1,639 ETH |
| 26JUN2026 | 56d | 43.10 | 2,034 ETH |
| 25SEP2026 | 147d | 13.86 | 360 ETH |

10× growth-rate progression from longest to shortest maturity. Verdict label: **`oi_ramps_toward_expiry`**. HYPERLIQUID-ETH shows the same monotonic pattern (sanity check). Panel B of the PNG (OI vs days-to-expiry, all 6 markets overlapped) shows the curve accelerating sharply below ~50 days.

### What this DOES NOT mean — fill-risk parity correction

Initial reading was *"sept25 will get a 4× budget lift as it ages into front-month, so the lifetime APR is 700–900% not 415%."* That's wrong. The OI ramp is driven by the *same mechanism* that drives fill-risk: rate-traders concentrating activity near expiry. The structural relationship between Daily Volatility, incentivized-range width, and fill probability — measured directly from the dapp:

| market | maturity | Daily Vol | range width | 1σ-daily / range-width | implication for fill avoidance |
|---|---|---|---|---|---|
| may29 | 28d | ±1.35% | 0.67% | **2.0×** | 1σ daily move blows through entire range every day |
| jun26 | 56d | ±0.47% | ~0.35% | **1.3×** | edges crossed often |
| sept25 | 147d | ±0.34% | 0.63% | **0.5×** | 1σ move is half the range; edges rarely crossed |

Daily Volatility scales inversely with duration — a structural fact, not a snapshot. Therefore as sept25 ages into front-month status (~late Aug 2026, ~28d-out), its Daily Vol will rise toward the ~±1.35% regime *in proportion to* the budget lift. **Net strategy yield from the front-month transition is approximately a wash, possibly slightly negative if fill-loss grows faster than budget**. There is no free 4× upside.

### Corrected binding-market rationale

`BINANCE-ETHUSDT-25SEP2026` is the right binding market — but for a different reason than Phase 05.1 stated. The defensible reasoning:

1. **Structural fill-avoidance**: Daily-vol-to-range-width ratio of 0.5× is the lowest of any Boros ETH market right now. Strategy is fundamentally a fill-avoidance play; sept25 is the structurally safest environment.
2. **Sufficient ship-gate margin**: 415% USD-APR (CONTEXT.md prediction) clears the 6% USD-APR threshold by ~70× even at the current low-budget regime. The gate doesn't need maximization — it needs decisive PASS.
3. **Runway**: 4 months until expiry leaves time for the strategy to compound at the safe regime before the front-month vol spike.

### Implication for Phase 6 strategy operations

The OI / Daily-Vol curves together imply a **roll-out rule**: when the binding-market days-to-expiry drops below ~60d (or equivalently, when measured Daily Vol crosses some threshold like ±0.6%), open a fresh long-dated position and migrate. The strategy never camps in the front-month spicy zone. Concrete next steps for Phase 6:

- Add `roll_out_trigger_days_to_expiry` knob (default ~60) to `BotConfig`
- Add `roll_out_trigger_daily_vol_pct` knob (default ~0.6%) as the alternative trigger
- Bot opens fresh position in the longest-dated available ETH market when trigger fires
- Closes binding-market position via voluntary cancel (per P0-01 resolution: rewards aren't forfeited)

### Implications for CONTEXT.md framing

The "~415% USD-APR" Phase 05.2 prediction stays. The earlier session's optimistic "lifetime average 700–900% USD-APR" framing — which I'd briefly suggested before this fill-risk audit — is **WITHDRAWN**. Phase 05.2's predicted verdict is 415% USD-APR floor (current low-budget, low-fill-risk regime), and that's the regime the strategy will run in for the bulk of sept25's lifetime under the roll-out rule.
