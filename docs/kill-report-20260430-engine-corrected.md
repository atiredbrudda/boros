# Phase 05.2 Ship-Gate: Engine-Corrected Re-Run FAIL Verdict (DRAFT — NOT COMMITTED)

**Status:** DRAFT — prepared for operator review. This is the FAIL branch write-up.
The observed verdict is PASS (p5=9.71, threshold=0.06). This document is prepared
per the plan protocol but is NOT the correct branch to commit.

**NOTE TO OPERATOR:** The actual verdict is PASS (p5=970.6% USD-APR). The correct
document to commit is `docs/halt-lift-20260430.md`. This FAIL draft is here only
for completeness per the checkpoint protocol.

**If halt continues:** Status remains `halted_pending_phase_05_2`. Bug #6 candidate
(effective-pool weighting) would be the next investigation.

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

## Bug #6 Candidate (queued as non-blocking investigation)

**Hypothesis A (highest ranked):** Effective-pool weighting. Pendle computes a weighted
effective pool that does not equal the raw CLO-range sum from `order_book_raw`. The engine
uses the raw sum (~165 YU) while the empirical effective pool may be ~75 YU. At p5=970%,
this discrepancy is beneficial (our share is larger than predicted) but the underlying
model doesn't match the protocol. Phase 6 calibration should validate.

[[ship-gate-verdict-20260430-engine-corrected]]
[[ship-gate-verdict-20260429-stale-inputs]]
