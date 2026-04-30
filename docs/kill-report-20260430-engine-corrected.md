# Phase 05.2 Ship-Gate: Engine-Corrected Re-Run FAIL Verdict (DRAFT — NOT COMMITTED)

> **STATUS 2026-04-30: SUPERSEDED.** This draft was written under the assumption that the
> Wave 5 binding run's `p5 = 9.706` was a real PASS overshoot. Operator review showed the
> verdict was inflated by an undiagnosed sixth bug — the calibration reader was not
> `effective_at_utc`-keyed and applied the current-epoch `long_side_split = 0.760` to
> historical replay ticks where the real-world split was ≈ 0.327. The Bug-#6-candidate
> sketched below (Pendle effective-pool weighting) was the *wrong* hypothesis and is
> retracted. The actual Bug #6 has been fixed; the binding ship-gate is pending a re-run.
>
> See `[[ship-gate-bug-6-epoch-keyed-calibration]]`.

**Status:** ~~DRAFT — prepared for operator review. This is the FAIL branch write-up.
The observed verdict is PASS (p5=9.71, threshold=0.06). This document is prepared
per the plan protocol but is NOT the correct branch to commit.~~ SUPERSEDED — both the PASS draft (`halt-lift-20260430.md`) and this FAIL draft were premised on a verdict that has been invalidated. Neither will be committed as the binding routing.

~~**NOTE TO OPERATOR:** The actual verdict is PASS (p5=970.6% USD-APR). The correct
document to commit is `docs/halt-lift-20260430.md`. This FAIL draft is here only
for completeness per the checkpoint protocol.~~

**Halt status:** Remains `halted_pending_phase_05_2` until a clean re-run on the Bug-#6-fixed engine produces a binding verdict.

---

## Hypothetical FAIL Verdict Summary (for completeness — not applicable)

| metric | value |
|--------|-------|
| p5_annualized_pnl (5th-pct block-bootstrap, USD-APR fraction) | **9.706** (970.6% USD-APR) |
| threshold (alt_yield + all_fees, USD-APR fraction) | **0.0600** (6.00% USD-APR) |
| passed | **TRUE** — this document is the wrong branch |

**Run ID:** `01KQEZ6M0SWVXX3H4G5W7RNFS8`
**Parent Run ID:** `01KQDQG0D3TZNZS2QQAPTEAPYJ`

---

## ~~Bug #6 Candidate~~ — Retracted

> ~~Hypothesis A: Effective-pool weighting.~~ Retracted 2026-04-30. Plug
> `sigma_others = 165, side_split = 0.760, q_me = 4.92, e_liq = 309.96` into
> `r_share = e_liq × split × q_me / (sigma + q_me)` and the result is `≈ 4.78 USD-APR`,
> nowhere near the observed 9.71. Back-calc from `p5 = 9.706` requires `sigma ≈ 79 YU`,
> indistinguishable from the prediction's 75. The 2.34× overshoot lives entirely in the
> `side_split` term: `0.760 / 0.327 = 2.32×`. The actual Bug #6 is the calibration reader.

**Actual Bug #6 (fixed):** `_read_operator_calibration_sql` sorted by `calibrated_at_utc DESC LIMIT 1` and ran once at startup, applying the current-epoch row to the entire historical replay. Fix: `_calibration_at_chain_ts(chain_ts)` filters by `effective_at_utc <= chain_ts` and is called per tick. See `[[ship-gate-bug-6-epoch-keyed-calibration]]`.

[[ship-gate-bug-6-epoch-keyed-calibration]]
[[ship-gate-verdict-20260430-engine-corrected]] (Status: Historical — superseded)
[[ship-gate-verdict-20260429-stale-inputs]]
