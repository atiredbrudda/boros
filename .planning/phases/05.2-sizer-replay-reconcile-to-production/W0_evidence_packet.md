# Phase 05.2 — W0 Evidence Packet

**Collected:** <DATE-FILLED-BY-OPERATOR>
**Operator:** macbookair
**Status:** Current

## E1 — Cross-market trial-order probe (60 min)

### Market: BINANCE-ETHUSDT-29MAY2026 (28-day reference)

| side | size_yu | notional_eth | implied_apr_pct | rate_sensitivity_eth | margin_required_eth | while_active_pendle_per_day | when_filled_pendle |
|------|---------|--------------|-----------------|----------------------|---------------------|-----------------------------|--------------------|
| long | 0.1 | TBD | TBD | TBD | TBD | TBD | TBD |
| long | 0.45 | TBD | TBD | TBD | TBD | TBD | TBD |
| short | 0.1 | TBD | TBD | TBD | TBD | TBD | TBD |
| short | 0.45 | TBD | TBD | TBD | TBD | TBD | TBD |

Derived:
- margin_per_yu_usd: TBD (= margin_required_eth × eth_price_usd / size_yu)
- rate_sensitivity_per_yu_usd_per_pct: TBD

### Market: <HYPERLIQUID-MARKET-CHOSEN-BY-OPERATOR>

| side | size_yu | notional_eth | implied_apr_pct | rate_sensitivity_eth | margin_required_eth | while_active_pendle_per_day | when_filled_pendle |
|------|---------|--------------|-----------------|----------------------|---------------------|-----------------------------|--------------------|
| long | 0.1 | TBD | TBD | TBD | TBD | TBD | TBD |
| long | 0.45 | TBD | TBD | TBD | TBD | TBD | TBD |
| short | 0.1 | TBD | TBD | TBD | TBD | TBD | TBD |
| short | 0.45 | TBD | TBD | TBD | TBD | TBD | TBD |

Derived:
- margin_per_yu_usd: TBD (= margin_required_eth × eth_price_usd / size_yu)
- rate_sensitivity_per_yu_usd_per_pct: TBD

## E2 — Daily Volatility (binding market)

daily_volatility_pct: TBD

Source: orderbook header on https://boros.pendle.finance/markets/BINANCE-ETHUSDT-25SEP2026 as of <TIMESTAMP-UTC>

## E3 — Time-stability check (binding market reward statistics)

Reading 1 (T0):
- timestamp_utc: TBD
- long_pendle_per_day: TBD
- short_pendle_per_day: TBD

Reading 2 (T0 + 6-12h):
- timestamp_utc: TBD
- long_pendle_per_day: TBD
- short_pendle_per_day: TBD

Drift:
- e3_drift_pct: TBD (= 100 × |long_2 - long_1| / long_1)
- e3_recommended_cadence: TBD (weekly if <5% / epoch_aligned if >20% / weekly_with_alert if 5-20%)

## E5 — Pendle docs URL (bonus)

e5_url: TBD (or NOT_FOUND)

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
