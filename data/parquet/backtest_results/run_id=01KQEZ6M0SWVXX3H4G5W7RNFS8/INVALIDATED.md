# Run 01KQEZ6M0SWVXX3H4G5W7RNFS8 — INVALIDATED

**Date invalidated:** 2026-04-30

The `ship_gate_verdict.json` in this directory reports `p5_annualized_pnl = 9.706499...`
(`970.6% USD-APR`). That number is **not** a clean reflection of strategy economics on
the 26-day historical replay window. It was inflated by a sixth engine bug, undiagnosed
when the run completed, that survived past Wave 5's "all 5 bugs fixed" claim.

## Bug

`backtest/replay.py:_read_operator_calibration_sql` ordered operator rows by
`calibrated_at_utc DESC LIMIT 1` and was invoked once at run start. The single row was
applied to every tick. The Wave 2b row insert had populated:

| effective_at_utc       | long_side_split |
|------------------------|-----------------|
| 2026-04-18 (prior)     | 0.327           |
| 2026-04-25 (current)   | 0.708 / 0.760   |

`calibrated_at_utc DESC` picked the current-epoch row regardless of which epoch a given
tick's `chain_ts` fell into. The 26-day historical replay (predominantly within the prior
epoch) was evaluated as if the strategy had earned the current-epoch reward split for the
whole window.

Inflation: `0.760 / 0.327 = 2.32×`, exact match to the observed `2.34×` overshoot vs the
falsifiable `~415%` prediction.

## Math sanity-check

Reward formula: `r_share/epoch = e_liq × split × q_me / (sigma + q_me)`.

Engine inputs in this run: `e_liq = 309.96, split = 0.760, q_me = 4.92`. With observed
`p5 = 9.706 USD-APR`, back-calc gives `sigma ≈ 79 YU` — indistinguishable from the
prediction's `~75 YU`. The "Bug #6 hypothesis A" framing in `docs/halt-lift-20260430.md`
(claiming the engine used raw `sigma_others = 165`) is mathematically incompatible with
this verdict and has been retracted.

## What this means for strategy viability

The strategy economics still appear viable. Algebraic prediction for a clean re-run on the
Bug-#6-fixed engine: `970% / 2.32 ≈ 418% USD-APR ≈ predicted 415%`, ~70× the 6% threshold.
But the binding ship-gate verdict must come from a clean run, not from rescaling this one.

## Fix

`_calibration_at_chain_ts(chain_ts)` filters operator rows by
`effective_at_utc <= chain_ts` and is called per `_build_evaluate_input`. Tests in
`python/tests/test_calibration_chain_ts_aware.py`.

## Cross-references

- Wiki: `[[ship-gate-bug-6-epoch-keyed-calibration]]`
- Halt-lift draft (now invalidated): `docs/halt-lift-20260430.md`
- FAIL draft (now superseded): `docs/kill-report-20260430-engine-corrected.md`
- Phase summary amendment: `.planning/phases/05.2-sizer-replay-reconcile-to-production/05.2-07-SUMMARY.md`
