---
phase: 04-decision-engine-predictive-circuit-breakers
reviewed: 2026-04-25T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - python/src/boros_brain/decision/breakers/maturity.py
  - python/tests/test_breaker_maturity.py
  - python/tests/test_main_decision_loop_spawn.py
  - python/tests/test_manifest_contains_all_knobs.py
  - docs/architecture.yml
  - docs/ARCHITECTURE.md
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 4: Code Review Report (Gap-Closure Plans 04-07 / 04-08)

**Reviewed:** 2026-04-25
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Six files reviewed across the gap-closure wave for Phase 4 (Plans 04-07 and
04-08). The primary changes are: making `gas_cache` mandatory in
`MaturityBreaker`, replacing the old `gas_cache=None` test path with a
`_FakeGasCache` stub, fixing the bound-method `is` assertion in the halt
callback test, fixing dict-knob traversal in the manifest round-trip test,
and recording the new `maturity → gas_history` edge in both architecture
files.

The mandatory-injection refactor in `maturity.py` is mechanically correct
and the DECIDE-03 invariant is now enforced on the live code path. The
`_FakeGasCache` stub is appropriate. The `__func__`/`__self__` bound-method
fix in `test_main_decision_loop_spawn.py` is correct. The `_walk_dict_paths`
fix in `test_manifest_contains_all_knobs.py` is correct.

Two warnings and two info items are noted below.

---

## Warnings

### WR-01: `market_matured` early-return bypasses `gas_cache` call but `_gas_cache` is never validated as non-None at init

**File:** `python/src/boros_brain/decision/breakers/maturity.py:58-59`

**Issue:** `__init__` accepts `gas_cache: Any` and stores it without a
null-guard. If a caller accidentally passes `gas_cache=None` (e.g. a future
test or a coordinator bug), the failure surfaces only at line 104 as an
`AttributeError: 'NoneType' object has no attribute 'cancel_cost_pendle'` —
not at construction time. The error message will be cryptic and the line
trace will point inside `check()`, not at the call site that passed `None`.
The module docstring explicitly states "mandatory argument — there is no
`gas_cache=None` default", but the runtime provides no enforcement.

**Fix:**
```python
def __init__(self, gas_cache: Any) -> None:
    if gas_cache is None:
        raise TypeError(
            "MaturityBreaker: gas_cache is mandatory (DECIDE-03). "
            "Pass a GasHistoryCache instance or a _FakeGasCache test stub."
        )
    self._gas_cache = gas_cache
```

This converts a confusing mid-`check()` `AttributeError` into a clear
`TypeError` at construction, consistent with the module's documented contract.

---

### WR-02: `epoch_days` zero-division is unguarded — `ZeroDivisionError` possible if config is misconfigured

**File:** `python/src/boros_brain/decision/breakers/maturity.py:83`

**Issue:** `epochs_remaining = time_to_mat_s / (config.reward_share_model.epoch_days * 86400)`. If `epoch_days` is 0 (schema validation may or may not prevent this depending on whether the field has a `gt=0` constraint), this raises an unhandled `ZeroDivisionError` that propagates out of `check()`. The Breaker ABC contract expects `check()` to return a `BreakerSignal`, never raise. A misconfigured `epoch_days=0` would crash the decision loop.

**Fix:** Add a guard and return a safe signal, or verify the Pydantic field has a `gt=0` validator and document that reliance explicitly:
```python
epoch_s = config.reward_share_model.epoch_days * 86400
if epoch_s <= 0:
    return BreakerSignal(
        tripped=False,
        reason="invalid_epoch_days_config",
    )
epochs_remaining = time_to_mat_s / epoch_s
```

If the schema already enforces `gt=0` on `epoch_days`, a single-line assert
with a descriptive message is acceptable in place of the guard:
```python
assert config.reward_share_model.epoch_days > 0, (
    "epoch_days must be > 0 (enforced by Pydantic schema)"
)
```

---

## Info

### IN-01: `market_matured` branch is not covered by any test case

**File:** `python/tests/test_breaker_maturity.py` (whole file)

**Issue:** `test_breaker_maturity.py` has three tests covering:
(1) remaining < migration cost, (2) remaining > migration cost, and (3) no
decision history. There is no test for the `time_to_mat_s <= 0` branch (line
76–81 of `maturity.py`) which returns `ROLL_POSITION` with
`reason="market_matured"`. This is a distinct code path and the most urgent
signal the breaker can emit; missing coverage here means a regression in that
branch would go undetected.

**Fix:** Add a fourth test:
```python
@pytest.mark.asyncio
async def test_fires_when_market_already_matured(
    tmp_path, default_config, tmp_sqlite_path
):
    """SAFE-07: market_ts in the past → tripped=True, reason='market_matured'."""
    config = _config_with_market(default_config, CURRENT_TS - 1)  # past maturity
    breaker = MaturityBreaker(gas_cache=_FakeGasCache())
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=CURRENT_TS,
    )
    assert sig.tripped is True
    assert sig.reason == "market_matured"
    assert sig.kill_command_kind == "ROLL_POSITION"
```

---

### IN-02: `test_decision_loop_task_created` does not actually call `brain_main.run()` — structural test only

**File:** `python/tests/test_main_decision_loop_spawn.py:72-142`

**Issue:** The test defines and executes its own `_fast_boot` coroutine that
reconstructs the relevant plumbing manually, rather than invoking
`brain_main.run()`. The structural test `test_decision_loop_function_defined`
(line 41) covers source-inspection of `run()`. However `test_decision_loop_task_created` as written actually tests that the test's own local `_fast_boot` correctly creates a task — not that `brain_main.run()` does. If the wiring inside `brain_main.run()` is broken (e.g. task created under a different name, or creation skipped under certain boot conditions), this test would still pass.

**Fix:** This is a known architectural constraint (cannot easily call `run()` in test due to ZMQ/RPC boot). The limitation is partially acknowledged in the test docstring. The recommendation is to add a comment making it explicit that this test validates the *local* task-spawn plumbing as a proxy, and that the structural source-inspection in `test_decision_loop_function_defined` is the primary `run()` contract guard — so a future reader does not mistake one for the other. No code change strictly required, but the distinction should be documented inline.

---

_Reviewed: 2026-04-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
