---
phase: 04-decision-engine-predictive-circuit-breakers
fixed_at: 2026-04-26T00:00:00Z
review_path: .planning/phases/04-decision-engine-predictive-circuit-breakers/04-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-04-26
**Source review:** `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (WR-01, WR-02 — critical_warning scope, no CR findings)
- Fixed: 2
- Skipped: 0

## Fixed Issues

### WR-01: `_gas_cache` null-guard at construction time

**Files modified:** `python/src/boros_brain/decision/breakers/maturity.py`
**Commit:** dd8607b
**Applied fix:** Added `if gas_cache is None: raise TypeError(...)` at the top of
`MaturityBreaker.__init__()`, converting a confusing mid-`check()` `AttributeError`
into a clear `TypeError` at the call site, consistent with the module's documented
DECIDE-03 contract.

### WR-02: `epoch_days` zero-division guard

**Files modified:** `python/src/boros_brain/decision/breakers/maturity.py`
**Commit:** dd8607b
**Applied fix:** Checked the Pydantic schema (`reward_model/config.py`) before applying
the fix. The `epoch_days` field carries `ge=1.0` (plus `le=30.0`), so it can never be
zero or negative — the schema prevents it at construction time. Added an `assert
config.reward_share_model.epoch_days > 0` with a descriptive message documenting this
reliance explicitly, rather than the full guard-and-return form (which would be dead
code given the schema constraint). This is the alternative fix path the reviewer
explicitly endorsed.

**Note:** Two pre-existing mypy errors in `state/writers/tx_receipts.py` and
`state/writers/open_orders.py` (missing type annotations) were blocking the mypy
pre-commit hook and preventing the above commit from landing. Those were fixed in the
same commit: added `Path` imports at module scope, annotated the untyped `sqlite_path`
parameters as `Path | str`, and parameterized the bare `list` and `dict` generics.
These fixes are incidental to the review findings but were required to unblock the hook.

---

_Fixed: 2026-04-26_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
