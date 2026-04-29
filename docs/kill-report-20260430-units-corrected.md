# Phase 5.1 Ship-Gate: Units-Corrected Re-Run FAIL Verdict

**Status:** Final — fresh end-to-end run on units-fixed code confirms the analytical correction within MC error.

**Decision:** HALT CONTINUES — Phase 5.1 ship-gate FAIL stands. Strategy yield in defensible USD-APR units (~0.033%) is two orders of magnitude below the 6% USD-APR threshold.

## Context

The two prior runs on 2026-04-29 (`01KQB9CPQAQS31P2ZSY14DHYH6` and `01KQDMC1DC3JW07VG2VMKKXM6T`) reported their verdict in **incoherent units** — `p5_annualized_pnl` was a raw PENDLE-per-year quantity (no division by capital), but it was compared against `threshold = screener.alt_yield + backtest.all_fees_threshold = 0.06`, which is a USD-APR fraction. The labels `% APR` in those reports are mathematically wrong.

This run regenerates the verdict in correct USD-APR units after a one-line fix to the replay aggregator.

### Bug summary (audit 2026-04-30)

`backtest/replay.py:_aggregate_daily_pnl` returned `daily_pnl` in **PENDLE per day** with no collateral denominator. `backtest/bootstrap.py:block_bootstrap_pnl` annualized that as `sample.sum() × 365 / n_days`, yielding **PENDLE per year** — a raw quantity, not a rate. `backtest/ship_gate.py:evaluate_ship_gate` then compared that quantity against a USD-APR fraction, producing a unit-incoherent verdict.

Phase 1's `screener/economics_gate.py:9-14` waved the same fudge off with a "USD conversion deferred to Phase 3" caveat. Phase 3 wired `pendle_price_usd` into the **sizer** (`sizer/optimizer.py:58, 104`) but never wired it back into the backtest P&L unit. The Phase 5.1 ship-gate inherited the latent unit mismatch *and* additionally lost the capital-normalization step entirely.

### Fix

`_aggregate_daily_pnl` now multiplies the daily PENDLE bins by `pendle_price_usd / collateral_usd` before returning, producing a daily fraction of USD collateral. After bootstrap annualization, `p5_annualized_pnl` is a USD-APR fraction directly comparable to `screener.alt_yield + backtest.all_fees_threshold`. The conversion is a positive linear scalar, so percentile order is preserved (Δsign of every pairwise comparison is unchanged) — the perturbation grid's fragile-knob count is invariant under this fix.

Tests in `python/tests/test_backtest_replay_daily_pnl.py` were updated to assert the new contract; tests in `test_backtest_ship_gate_*` and `test_backtest_bootstrap_idempotent` did not need changes — their hand-crafted `daily_pnl` arrays were already in daily-fraction units (the test author understood the contract; the production replay violated it).

## Analytical Pre-Confirmation

Because the conversion is a positive linear scalar and `np.percentile` is order-preserving under positive linear transformation, the corrected verdict can be derived from the prior run analytically:

```
p5_corrected     = p5_old × (pendle_price_usd / collateral_usd)
                 = 0.024401181808589217 × (1.35 / 100.0)
                 = 0.0003294160 USD-APR fraction (= 0.0329% USD-APR)
threshold        = 0.06 USD-APR fraction (unchanged)
delta            = −0.0596706 (= −5.97 ppt)
passed           = false
```

The fresh run below should land within ~1.5% MC error of this number (different bootstrap seed → different ULID → different RNG draws, but same unit semantic).

## Verdict Summary (Fresh Run)

| metric | value |
|--------|-------|
| p5_annualized_pnl (5th-pct block-bootstrap, USD-APR fraction) | **0.0003339** (0.0334% USD-APR) |
| threshold (alt_yield + all_fees, USD-APR fraction) | **0.0600** (6.00% USD-APR) |
| delta | **−0.0597** (−5.97 ppt) |
| passed | **false** |
| n_resamples | 2000 |
| block_seconds | 86400 (1-day blocks) |
| RNG seed | 18197629191823121362 |
| n_fills | 0 |

**Run ID:** `01KQDQG0D3TZNZS2QQAPTEAPYJ`
**Parent Run ID:** `01KQDMC1DC3JW07VG2VMKKXM6T` (units-incoherent re-run)
**Grandparent Run ID:** `01KQB9CPQAQS31P2ZSY14DHYH6` (original input-stale FAIL)
**Git SHA at run time:** `d05e83b5b902b06cf5d346e46b276a92fb62667c` (with replay.py units fix dirty in working tree — `git_dirty: True` is honestly stamped in the manifest; the units fix lands in the next commit)
**Timestamp (UTC):** `2026-04-29T23:02:06.941816+00:00`
**Market:** `BINANCE-ETHUSDT-25SEP2026` (long side, highest-conviction shortlist market)

### Analytical-vs-empirical agreement check

| | analytical (from 01KQDMC1DC3JW07VG2VMKKXM6T × c) | fresh in-run (01KQDQG0D3TZNZS2QQAPTEAPYJ) | MC error |
|--|--|--|--|
| p5 (USD-APR fraction) | 0.0003294 | 0.0003339 | +1.4% |
| % USD-APR | 0.0329% | 0.0334% | — |
| delta (ppt) | −5.967 | −5.967 | — |
| passed | false | false | — |

The 1.4% discrepancy on p5 sits within the expected ~1.5% MC error from a 2000-sample bootstrap on the 5th percentile (different ULID → different RNG seed → different resample draws). Verdict direction and gap-to-threshold are stable.

## Comparison Across All Three Runs

| metric | original (input-stale, PENDLE-units) | re-run (corrected inputs, PENDLE-units) | this run (corrected units) |
|--------|--------------------------------------|----------------------------------------|----------------------------|
| reported `p5_annualized_pnl` | 0.0049 | 0.0244 | 0.000334 |
| reported "% APR" label | "0.49% APR" | "2.44% APR" | "0.0334% USD-APR" |
| reported gap to threshold | −5.51 ppt | −3.56 ppt | −5.97 ppt |
| **true USD-APR** (analytical) | ~0.0034% (= 0.0049 × 7/100) | 0.0329% | 0.0334% (in-run, matches analytical 0.0329% within MC error) |
| **true gap** | −5.997 ppt | −5.967 ppt | −5.967 ppt |
| FAIL verdict direction | FAIL | FAIL | FAIL |

(`c = pendle_price_usd / collateral_usd`; for the original run the price was the 7.0 default, and for the re-run it was 1.35.)

The "input fix lifted p5 by ~4.98×" claim in the prior kill-report (0.49% → 2.44%) **was correct in PENDLE/year units** — the sizer used `pendle_price_usd` to compute `q_me_pendle`, which changed `q_me / (sigma_others + q_me)` and thus the reward share. The ratio of the two PENDLE/year numbers correctly reflects the sizing-side improvement. What the kill-report got wrong was labelling either number "% APR" — neither was an APR.

In USD-APR units the actual gap-to-threshold has been roughly stable across all three runs at ~−6 ppt: the strategy is producing ~0.03% USD-APR on $100 collateral against a 6% USD-APR threshold. The "5× improvement from the price fix" was real, but on a denominator so small that even the corrected number is two orders of magnitude below threshold.

## Implication for the "Engine Completeness" Recovery Path

The 05.1-05 SUMMARY estimated that fixing the sparse-event tick under-counting could plausibly recover a factor of ~2-3× on a 3-trade-per-day market, with a best-case "10×" reward-rate increase that "might bring p5 to ~5-7% APR". That estimate was made against the units-incoherent number; against the units-corrected baseline of **0.033% USD-APR**, the same multipliers project to **0.07% – 0.33% USD-APR** — still 18–86× below the 6% threshold.

Conclusion: even with the most generous engine-completeness fix, the strategy at $100 collateral / $1.35 PENDLE on the BINANCE-ETHUSDT-25SEP2026 long shortlist position is structurally below threshold. Recovery requires either (a) a much larger collateral base, (b) a market with a much higher reward-rate / competition ratio, or (c) something the backtest is materially undercounting beyond sparse-tick.

## Implication for the Dashboard Discrepancy

The dapp dashboard shown by the operator claims ~1000% USD-APR for similar markets. The backtest now reports ~0.033% USD-APR. The gap is ~30,000× — far beyond what any plausible engine-completeness fix can close. Two non-exclusive hypotheses worth investigating before any further engineering:

1. **Definition mismatch.** Dashboard APR may be (a) per-position not per-collateral (1000% on the position notional ≈ a much smaller % on collateral), (b) before fees / slippage / fill-loss, (c) inclusive of a fresh-market/IL referral bonus the backtest doesn't model, or (d) annualized off a peak short-window reward rate, not a sustained mean.

2. **`q_me / sigma_others` mis-estimate.** Backtest's competition denominator may be too large by 2-3 orders of magnitude — pulling `sigma_others` from the wrong column, or summing across markets, or counting taker-side liquidity that doesn't compete for the LO reward pool.

Both are cheap to verify (~hours each). Either one resolved would explain the 30,000× gap without further engine work.

## Threshold Components

| component | value |
|-----------|-------|
| `screener.alt_yield` | 0.0500 |
| `backtest.all_fees_threshold` | 0.0100 |
| **Total** | **0.0600** |

## Loss Model Status

(Inherited from re-run `01KQDMC1DC3JW07VG2VMKKXM6T` — code paths unchanged from that commit.)

| market_id | side | fit_status | n_fills | n_cells |
|-----------|------|------------|---------|---------|
| BINANCE-ETHUSDT-25SEP2026 | long | ok | 12 | 1 |
| BINANCE-ETHUSDT-25SEP2026 | short | degraded | 2 | 1 |

## Remaining Engine-Completeness Caveat (unchanged)

Sparse-event tick under-counting is still unfixed. Per the analysis above, fixing it does not recover viability on this position. Documented for completeness.

## Provenance

| artifact | path |
|----------|------|
| ship_gate_verdict.json | `data/parquet/backtest_results/run_id=01KQDQG0D3TZNZS2QQAPTEAPYJ/ship_gate_verdict.json` |
| ship-gate-report.md | `var/backtest/01KQDQG0D3TZNZS2QQAPTEAPYJ/ship-gate-report.md` |
| run manifest sidecar | `var/backtest/01KQDQG0D3TZNZS2QQAPTEAPYJ/01KQDQG0D3TZNZS2QQAPTEAPYJ.manifest.json` |
| backtest log | `logs/05.1-backtest-units-corrected.log` |
| code fix | `python/src/boros_brain/backtest/replay.py:_aggregate_daily_pnl` |
| bootstrap unit contract | `python/src/boros_brain/backtest/bootstrap.py:block_bootstrap_pnl` (docstring) |
| test contract | `python/tests/test_backtest_replay_daily_pnl.py` (4 tests) |
| wiki page | `[[ship-gate-units-bug-2026-04-30]]` |

## Supersedence

This kill-report supersedes:
- [docs/kill-report-20260429-rerun.md](kill-report-20260429-rerun.md) — units-incoherent verdict, status flips to historical
- [docs/kill-report-20260429.md](kill-report-20260429.md) — input-stale + units-incoherent verdict, already historical
