---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 08
type: execute
wave: 2
depends_on: [07]
gap_closure: true
autonomous: false
requirements: [DECIDE-03]
files_modified:
  - python/tests/test_main_decision_loop_spawn.py
  - var/phase4-pytest-greenrun-{run_id}.log

user_setup: []

must_haves:
  truths:
    - "The full Phase 4 pytest suite is GREEN against HEAD with output captured to a log file under `var/` for replay."
    - "`python/tests/test_main_decision_loop_spawn.py::test_chain_cache_halt_callback_wired` passes by asserting bound-method functional equivalence (`__func__` and `__self__`) instead of `is` identity — Python re-binds methods on each attribute access, so the previous `is` assertion was structurally broken regardless of the wiring."
    - "The Phase 4 'all-tests-green' pivot point is documented in a SUMMARY with the captured log file path, commit hash, and pytest pass-count — operator has a single artifact to cite when starting Phase 5."
    - "VERIFICATION.md Human Verification item #1 (full pytest run confirmation) is closed."
  artifacts:
    - path: "python/tests/test_main_decision_loop_spawn.py"
      provides: "Fixed bound-method identity assertion using __func__ + __self__ equivalence"
      contains: "__func__"
    - path: "var/phase4-pytest-greenrun-{run_id}.log"
      provides: "Captured pytest output for replay/audit"
      contains: "passed"
  key_links:
    - from: "python/tests/test_main_decision_loop_spawn.py"
      to: "python/src/boros_brain/decision/breaker_coordinator.py"
      via: "halt_via_chain_time bound-method functional equivalence assertion"
      pattern: "halt_via_chain_time"
---

<objective>
Close VERIFICATION.md Human Verification item #1 — confirm the full Phase 4 pytest suite is GREEN against HEAD (after Plan 04-07 has landed). The verifier could not flush pytest stdout to disk within its context budget; the operator now needs a single, replay-able artifact to confirm the suite is green before pivoting to Phase 5.

Secondary purpose: fix the documented `test_chain_cache_halt_callback_wired` bound-method identity quirk. The 04-06 SUMMARY framed this as "test design issue, not a code bug" and accepted the failure. The actual problem is structural: in Python, `coord.halt_via_chain_time` produces a NEW bound-method object on each attribute access (the descriptor protocol re-binds), so `cc.halt_callback is coord.halt_via_chain_time` is ALWAYS False even when the wiring is exactly correct. The fix is to compare `__func__` and `__self__` (which are stable across attribute accesses) — a 2-line change that makes the test actually verify the wiring contract rather than a Python-internal identity invariant.

This plan deliberately runs in Wave 2 (after 04-07) because:
1. 04-07's MaturityBreaker test refactor changes the test fixture surface — running the suite before 04-07 lands would surface the same gap a second time without progress.
2. The test fix in this plan is independent of 04-07 (different file, different concern), but bundling them lets the operator have a single "green-pivot" commit rather than two scattered ones.

The plan is `autonomous: false` — Task 2 (the pytest greenrun) is gated by an operator confirmation checkpoint because the verifier in VERIFICATION.md explicitly flagged this as Human Verification (their environment couldn't capture pytest stdout). The executor automates everything and lands at a checkpoint where the operator confirms the captured output before the SUMMARY is written.

Purpose: Document the all-green pivot point. Make the operator's Phase-5 starting state crisp and auditable.

Output: Bound-method test fix + captured pytest log under `var/` + SUMMARY citing both as Evidence.
</objective>

<execution_context>
@$HOME/.claude-personal-personal/get-shit-done/workflows/execute-plan.md
@$HOME/.claude-personal-personal/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@CLAUDE.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-VERIFICATION.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-06-coordinator-mainpy-predeploy-gate-shipgate-SUMMARY.md

# Files this plan touches
@python/tests/test_main_decision_loop_spawn.py
@python/src/boros_brain/decision/breaker_coordinator.py

<interfaces>
<!-- The bound-method fix needs these contracts. -->

From python/src/boros_brain/decision/breaker_coordinator.py (line 280+ approx):
```python
class BreakerCoordinator:
    async def halt_via_chain_time(self, *, drift_s: float, chain_ts: int) -> None:
        """Route ChainTimeCache halt through the KILL lane."""
        ...
```

Python bound-method semantics (the reason the original `is` assertion fails):

```python
# Each attribute access produces a NEW bound-method instance:
m1 = coord.halt_via_chain_time
m2 = coord.halt_via_chain_time
assert m1 is m2          # FALSE — two distinct bound-method objects
assert m1 == m2          # TRUE  — equality compares __func__ + __self__
assert m1.__func__ is m2.__func__  # TRUE — the underlying function is the same
assert m1.__self__ is m2.__self__  # TRUE — the receiver is the same
```

The test contract we want to verify is functional equivalence — "the callback IS coord's halt_via_chain_time method bound to this exact coord instance" — which is exactly what `__func__ is BreakerCoordinator.halt_via_chain_time` AND `__self__ is coord` proves.

Existing test code at line 184 (the assertion to fix):
```python
assert cc.halt_callback is coord.halt_via_chain_time, (
    "halt_via_chain_time must be assignable as a callback attribute"
)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix the bound-method identity assertion in test_chain_cache_halt_callback_wired</name>
  <files>python/tests/test_main_decision_loop_spawn.py</files>
  <read_first>
    - python/tests/test_main_decision_loop_spawn.py (the full file — 188 lines; the broken assertion is at line 184)
    - python/src/boros_brain/decision/breaker_coordinator.py (find the `halt_via_chain_time` method definition and confirm it's an `async def` on the class — needed for the `__func__` assertion)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-06-coordinator-mainpy-predeploy-gate-shipgate-SUMMARY.md (the SUMMARY documenting this as a known test-design issue; reference for the reasoning)
  </read_first>
  <behavior>
    Test 1 (`test_chain_cache_halt_callback_wired`): after assigning `cc.halt_callback = coord.halt_via_chain_time`, the callback must be functionally equivalent to `coord.halt_via_chain_time`:
    - `cc.halt_callback.__func__ is BreakerCoordinator.halt_via_chain_time` (or, equivalently, `is coord.halt_via_chain_time.__func__`).
    - `cc.halt_callback.__self__ is coord`.
    - `asyncio.iscoroutinefunction(cc.halt_callback)` is True.
    Test 2 (`test_decision_loop_function_defined`, line 41) — UNCHANGED, must still pass.
    Test 3 (`test_build_evaluate_input_helper_exists`, line 64) — UNCHANGED, must still pass.
    Test 4 (`test_decision_loop_task_created`, line 71) — UNCHANGED, must still pass.
  </behavior>
  <action>
**Sub-step 1A — locate the broken assertion:**

Open `python/tests/test_main_decision_loop_spawn.py`. The `test_chain_cache_halt_callback_wired` function spans lines ~145-188. The broken assertion is at line ~184:

```python
assert cc.halt_callback is coord.halt_via_chain_time, (
    "halt_via_chain_time must be assignable as a callback attribute"
)
```

**Sub-step 1B — replace with a functional-equivalence assertion:**

Replace the single broken `is` assertion with three explicit checks that match the actual wiring contract:

```python
# Bound methods are re-created on each attribute access — `is` would fail
# even when the wiring is correct. Compare the underlying function and the
# bound receiver instead, which are stable across accesses.
assert cc.halt_callback.__func__ is BreakerCoordinator.halt_via_chain_time, (
    "halt_callback must wrap BreakerCoordinator.halt_via_chain_time "
    "(got function %r)" % (cc.halt_callback.__func__,)
)
assert cc.halt_callback.__self__ is coord, (
    "halt_callback must be bound to the coord instance "
    "(got receiver %r, expected %r)" % (cc.halt_callback.__self__, coord)
)
assert asyncio.iscoroutinefunction(cc.halt_callback), (
    "halt_callback must be a coroutine function (chain_time awaits it)"
)
```

This requires `BreakerCoordinator` to be in scope. It already is — line 33 imports it (`BreakerCoordinator = breaker_coordinator_mod.BreakerCoordinator`). `asyncio` is imported at line 23.

**Sub-step 1C — update the test docstring (lines 151-156)** to reflect the new assertion strategy:

```python
"""BreakerCoordinator.halt_via_chain_time wires correctly as a chain_time halt callback.

Verifies functional equivalence (not Python `is` identity — bound methods are
re-created on each attribute access, so `is` would fail even when the wiring
is correct). The contract is: when ChainTimeCache assigns `halt_callback =
coord.halt_via_chain_time`, the resulting callable wraps the
BreakerCoordinator.halt_via_chain_time function bound to the same coord
instance, and is itself a coroutine function (so chain_time can `await` it).
"""
```

**Sub-step 1D — run the test inline:**

```bash
cd python && uv run python -m pytest tests/test_main_decision_loop_spawn.py -q --tb=short
```

All 4 tests in the file must PASS (no SKIPs unless `pytest.importorskip` legitimately skipped one). If any fail, inspect the diff — the only intentional change is to the assertion at line ~184 and its surrounding docstring.
  </action>
  <verify>
    <automated>cd python && uv run python -m pytest tests/test_main_decision_loop_spawn.py -q --tb=short</automated>
    <automated>grep -q '__func__ is BreakerCoordinator.halt_via_chain_time' python/tests/test_main_decision_loop_spawn.py</automated>
    <automated>grep -q '__self__ is coord' python/tests/test_main_decision_loop_spawn.py</automated>
    <automated>! grep -q 'cc.halt_callback is coord.halt_via_chain_time' python/tests/test_main_decision_loop_spawn.py</automated>
  </verify>
  <acceptance_criteria>
    - `cd python && uv run python -m pytest tests/test_main_decision_loop_spawn.py -q` exits 0; all 4 tests in the file PASS.
    - `grep -n '__func__ is BreakerCoordinator.halt_via_chain_time' python/tests/test_main_decision_loop_spawn.py` returns at least one match.
    - `grep -n '__self__ is coord' python/tests/test_main_decision_loop_spawn.py` returns at least one match.
    - `grep -n 'cc.halt_callback is coord.halt_via_chain_time' python/tests/test_main_decision_loop_spawn.py` returns no matches (the broken assertion is gone).
    - `grep -n 'asyncio.iscoroutinefunction(cc.halt_callback)' python/tests/test_main_decision_loop_spawn.py` returns at least one match.
  </acceptance_criteria>
  <done>
    The previously-failing test asserts the actual wiring contract using stable comparisons (`__func__`, `__self__`, `iscoroutinefunction`) instead of an unstable Python-internal identity. The 04-06 SUMMARY's "test design issue, not a code bug" caveat is now resolved.
  </done>
</task>

<task type="auto">
  <name>Task 2: Run the full Phase 4 pytest suite, capture output to var/, and verify GREEN</name>
  <files>var/phase4-pytest-greenrun-{run_id}.log</files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VERIFICATION.md (the Human Verification item — confirms what the operator needs to see)
    - python/pyproject.toml (read briefly to confirm uv-based test invocation; do NOT modify)
  </read_first>
  <action>
**Sub-step 2A — ensure the `var/` directory exists at repo root:**

```bash
mkdir -p var
```

(The repo already has `python/var/` and root-level `var/` per the gitignored `var/` directory pattern — confirm with `ls var/ 2>/dev/null`.)

**Sub-step 2B — generate a run_id and run the full Phase 4 pytest suite with output captured:**

```bash
RUN_ID=$(python3 -c "import ulid; print(ulid.new())" 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4().hex[:16])")
LOG=var/phase4-pytest-greenrun-${RUN_ID}.log
echo "run_id=${RUN_ID}" > "${LOG}"
echo "git_sha=$(git rev-parse HEAD)" >> "${LOG}"
echo "started_at=$(date -u +%FT%TZ)" >> "${LOG}"
echo "---" >> "${LOG}"

cd python && uv run python -m pytest tests/ --tb=short -q 2>&1 | tee -a "../${LOG}"
EXIT=${PIPESTATUS[0]}
cd ..
echo "---" >> "${LOG}"
echo "exit_code=${EXIT}" >> "${LOG}"
echo "ended_at=$(date -u +%FT%TZ)" >> "${LOG}"
echo "Captured pytest output to ${LOG} (exit ${EXIT})"
```

NOTES on running this command:
- The `tee` pipe ensures output flushes line-by-line (this was the verifier's exact failure mode — pytest's stdout was buffered when redirected naively, so use `tee` to force interactive flushing).
- If `ulid` is not installed, the fallback `uuid.uuid4().hex[:16]` is fine — this is just a unique-id for the log filename.
- If `${EXIT}` is non-zero, that's a regression. STOP and inspect the captured log for the failing test names. Do NOT proceed to Task 3.

**Sub-step 2C — confirm the captured log shows GREEN:**

```bash
tail -10 "${LOG}"
grep -E '^=+ .* passed' "${LOG}" | tail -1
grep -E '^=+ .* (failed|error)' "${LOG}" | head -5
```

Expected:
- The pytest summary line shows `N passed` (N >= 50 per the VERIFICATION.md expectation, with the exact number being whatever pytest reports). Per SUMMARYs, total Phase 4 collected tests were 258.
- Zero failed/errored tests after Plan 04-07 + Task 1 of this plan.
- If `xfail` or `skipped` tests exist, that's expected (RED-state importorskip patterns from Plan 04-01 may still skip in unrelated phase boundaries, and DBSL/IPC tests on macOS may skip if the runner detects unsupported conditions).

If any tests show `failed` or `error`, document them in a CHECKPOINT to the operator (next task) before continuing.
  </action>
  <verify>
    <automated>ls var/phase4-pytest-greenrun-*.log 2>/dev/null | head -1</automated>
    <automated>test -s var/phase4-pytest-greenrun-*.log</automated>
    <automated>grep -q 'exit_code=0' var/phase4-pytest-greenrun-*.log</automated>
    <automated>grep -q 'passed' var/phase4-pytest-greenrun-*.log</automated>
  </verify>
  <acceptance_criteria>
    - File `var/phase4-pytest-greenrun-{run_id}.log` exists and is non-empty.
    - The log contains a `git_sha=...` header line so the run is tied to a specific commit.
    - The log contains an `exit_code=0` footer line.
    - `grep -E 'failed|error' var/phase4-pytest-greenrun-*.log | grep -v '0 failed\|0 error\|in test'` returns no test-failure summary lines.
    - The pytest summary line in the log shows `N passed` with N >= 50.
  </acceptance_criteria>
  <done>
    The full Phase 4 pytest suite is GREEN against HEAD, the run is captured to a replay-able log file in `var/`, and the operator has an artifact to cite as the Phase 5 starting point.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Operator confirms the captured pytest greenrun log</name>
  <files>(checkpoint task — no files modified; operator inspects the var/phase4-pytest-greenrun-{run_id}.log captured in Task 2)</files>
  <action>(checkpoint:human-verify — see <how-to-verify> below for the exact operator inspection steps)</action>
  <verify>(checkpoint:human-verify — operator-driven; resume-signal gates Task 4)</verify>
  <done>Operator returns "approved" via resume-signal after confirming pytest exit_code=0 and all three lint guards exit 0.</done>
  <what-built>
    - Plan 04-07 closed the DECIDE-03 lint gap (mandatory gas_cache injection in MaturityBreaker).
    - Plan 04-08 Task 1 fixed the bound-method identity assertion in test_main_decision_loop_spawn.py.
    - Plan 04-08 Task 2 ran the full Phase 4 pytest suite and captured the output to `var/phase4-pytest-greenrun-{run_id}.log`.
  </what-built>
  <how-to-verify>
    1. Identify the captured log:
       ```bash
       ls -lt var/phase4-pytest-greenrun-*.log | head -1
       ```
    2. Inspect the log header (run_id, git_sha, started_at) and footer (exit_code, ended_at):
       ```bash
       LOG=$(ls -t var/phase4-pytest-greenrun-*.log | head -1)
       head -5 "$LOG"
       tail -5 "$LOG"
       ```
    3. Confirm the pytest summary line shows ALL tests passed (or, the only non-passed are `skipped`/`xfail` as expected from importorskip / platform-conditional patterns):
       ```bash
       grep -E '^=+.*passed' "$LOG" | tail -1
       grep -E 'failed|error' "$LOG" | grep -vE '0 (failed|error)|in test'  # should output nothing
       ```
    4. Confirm the lint guards still exit 0 against HEAD (these were the Phase 4 gates):
       ```bash
       python3 scripts/no_hardcoded_cancel_cost_lint.py; echo "lint $?"
       python3 scripts/architecture_lint.py; echo "arch $?"
       python3 scripts/no_threshold_dials_lint.py; echo "dials $?"
       ```
       All three must exit 0.
    5. Optionally re-run the full suite live to confirm reproducibility:
       ```bash
       cd python && uv run python -m pytest tests/ -q --tb=short | tail -20
       ```

    Expected outcome: pytest summary shows N passed, 0 failed, 0 error. Lint guards all exit 0. The captured log file in `var/` is the durable artifact for "Phase 4 went green at commit {sha}".
  </how-to-verify>
  <resume-signal>
    Type "approved" to proceed to Task 4 (write SUMMARY + commit), or describe any failures you observe (e.g., "test_X failed" or "lint Y exits 1") and the executor will diagnose / re-plan.
  </resume-signal>
</task>

<task type="auto">
  <name>Task 4: Commit the test fix + write SUMMARY citing the captured greenrun log</name>
  <files>(no new files — git commit + SUMMARY only; the SUMMARY itself is created via the standard plan-output mechanism)</files>
  <read_first>
    - var/phase4-pytest-greenrun-{run_id}.log (the captured greenrun — to extract the pass-count, git_sha, and run_id for the SUMMARY)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-07-maturity-breaker-cancel-cost-injection-refactor-SUMMARY.md (the prior plan's SUMMARY — for cross-reference in this SUMMARY's Evidence section)
  </read_first>
  <action>
**Sub-step 4A — confirm the only diff is the test file:**

```bash
git status
git diff --stat
```

Expected: only `python/tests/test_main_decision_loop_spawn.py` shows in the diff. The captured log file under `var/` is gitignored (per project convention; `.gitignore` should already exclude `var/`). Confirm with:
```bash
git check-ignore -v "var/phase4-pytest-greenrun-*.log" 2>&1 | head -2
```

If `var/` is NOT gitignored (rare — would surface during `git status`), do NOT add the log to the commit; reference it by path in the SUMMARY only. The log is operator-private replay material, not committed history.

**Sub-step 4B — commit the test fix atomically:**

```bash
git add python/tests/test_main_decision_loop_spawn.py
git commit -m "$(cat <<'EOF'
fix(04-08): replace `is` identity assertion with __func__/__self__ functional check

test_chain_cache_halt_callback_wired previously asserted
`cc.halt_callback is coord.halt_via_chain_time`, which is structurally broken
in Python: each attribute access on a method descriptor produces a new
bound-method object, so the `is` check fails even when the wiring is exactly
correct. The 04-06 SUMMARY documented this as "test design issue, not a code
bug" and accepted the failure.

This commit replaces the broken assertion with three stable checks:
- `cc.halt_callback.__func__ is BreakerCoordinator.halt_via_chain_time`
- `cc.halt_callback.__self__ is coord`
- `asyncio.iscoroutinefunction(cc.halt_callback)`

This actually verifies the wiring contract (the callback wraps the
BreakerCoordinator.halt_via_chain_time function bound to this exact coord
instance, and is awaitable) instead of a Python-internal identity invariant.

Closes Phase 4 VERIFICATION.md Human Verification item #1 (test design issue
documented in 04-06 SUMMARY).

Captured greenrun: var/phase4-pytest-greenrun-{run_id}.log (gitignored;
operator-replay material).
EOF
)"
```

If the commit triggers a pre-commit hook regression, do NOT use `--no-verify`; investigate. The commit should land cleanly because no source files (only a test) were touched.

Capture the commit hash:
```bash
git log -1 --pretty=oneline
```

**Sub-step 4C — write the SUMMARY:**

Create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md` documenting:

- **Status:** GREEN
- **Commit hash** of the test-fix commit (Task 4 output).
- **Captured greenrun log path:** `var/phase4-pytest-greenrun-{run_id}.log` with the embedded run_id and git_sha.
- **Pytest summary line** extracted from the log (e.g., `==== N passed in M.Ms ====`).
- **Lint exit-codes:** `no_hardcoded_cancel_cost_lint.py` = 0, `architecture_lint.py` = 0, `no_threshold_dials_lint.py` = 0.
- **VERIFICATION.md gap-closure status:**
  - Gap #1 (DECIDE-03 lint): closed by Plan 04-07 (cite that SUMMARY).
  - Human Verification #1 (full pytest GREEN confirmation): closed by this plan.
- **Operator pivot statement:** "As of commit {sha}, Phase 4 is fully green and ready for Phase 5 planning. The captured pytest log at {path} is the durable replay artifact."
- **Caveats / known issues:** any test that was SKIPPED legitimately (importorskip patterns), with line-count from the captured log so a future re-run can detect drift.

**Sub-step 4D — update STATE.md to flip Phase 4 to fully complete:**

Read `.planning/STATE.md` and update the "Current Position" + "Carried concern" sections to reflect Phase 4 closure:
- Status: was "context exhaustion at 91% (2026-04-25)" — change to "Phase 4 GREEN at {sha}; ready for Phase 5".
- Add a Decisions entry: `[2026-04-25 04-07/08] Phase 4 verification gap closed: maturity breaker refactored to mandatory gas_cache injection (DECIDE-03 lint GREEN); halt-callback test fixed to compare __func__/__self__ (no more bound-method-identity false negative); full pytest suite GREEN, captured to var/phase4-pytest-greenrun-{run_id}.log.`

Commit STATE.md separately (planning-doc commit, not source):
```bash
gsd-sdk query commit "docs(state): Phase 4 GREEN — gap closure 04-07/08 complete" .planning/STATE.md .planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md .planning/phases/04-decision-engine-predictive-circuit-breakers/04-07-maturity-breaker-cancel-cost-injection-refactor-SUMMARY.md
```

(If the 04-07 SUMMARY commit was already landed, drop it from this commit's path list.)
  </action>
  <verify>
    <automated>git log -1 --format=%s | grep -q '04-08'</automated>
    <automated>test -f .planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md</automated>
    <automated>grep -q 'GREEN' .planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md</automated>
    <automated>grep -q 'phase4-pytest-greenrun' .planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - The test fix is committed; `git log -1 --format=%s | grep -q '04-08'` returns true.
    - SUMMARY file at `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md` exists.
    - SUMMARY contains the captured greenrun log path, the test-fix commit hash, and the pytest-pass count extracted from the log.
    - SUMMARY explicitly cites VERIFICATION.md Human Verification item #1 as closed.
    - STATE.md's "Carried concern" section no longer shows the pytest-confirmation pending item.
  </acceptance_criteria>
  <done>
    Phase 4 has a documented all-green pivot point. The operator can cite the captured log path + commit hash when starting Phase 5 work, and the VERIFICATION.md gaps are fully resolved.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

This plan is a test fix + an operator-runnable verification step. No production code changes; no new external inputs; no trust boundaries crossed.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-08-01 | (none) | (test-only refactor + verification) | accept | No new external inputs, trust boundaries, or attack surface — change is internal refactor of an existing dependency-injection pattern. The test fix tightens an assertion to actually verify the existing wiring contract; the pytest greenrun is read-only operator verification. |
</threat_model>

<verification>
After Task 4:
- `cd python && uv run python -m pytest tests/test_main_decision_loop_spawn.py -q` → all 4 tests PASS.
- `cd python && uv run python -m pytest tests/ -q` → captured log shows ALL tests PASS (or only legitimate SKIP/xfail).
- `python3 scripts/no_hardcoded_cancel_cost_lint.py` → exit 0 (still GREEN from 04-07).
- `python3 scripts/architecture_lint.py` → exit 0 (still GREEN from 04-07).
- The captured log at `var/phase4-pytest-greenrun-{run_id}.log` contains exit_code=0 and the git_sha.
- VERIFICATION.md Human Verification item #1 is closed.
</verification>

<success_criteria>
1. **Test fix:** `python/tests/test_main_decision_loop_spawn.py::test_chain_cache_halt_callback_wired` passes with the new `__func__`/`__self__` assertions; no `is`-on-bound-method assertion remains.
2. **Captured greenrun:** `var/phase4-pytest-greenrun-{run_id}.log` exists with `exit_code=0` and a `git_sha=...` header; the operator can cite it as the Phase 4 closure artifact.
3. **Operator confirmation:** Task 3 checkpoint received "approved" from the operator.
4. **SUMMARY:** Plan SUMMARY documents the commit hash, the captured log path, and explicitly closes VERIFICATION.md Human Verification item #1.
5. **STATE.md updated:** Phase 4 closure recorded; "ready for Phase 5" pivot point documented.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-08-phase4-pytest-greenrun-and-halt-callback-test-fix-SUMMARY.md` documenting:
- Test-fix commit hash
- Captured greenrun log path with embedded run_id and git_sha
- Pytest summary line (e.g., `==== N passed in M.Ms ====`)
- Lint exit-codes (cancel_cost, architecture, threshold_dials all 0)
- VERIFICATION.md gap-closure mapping (Gap #1 → 04-07; Human Verification #1 → 04-08)
- Operator pivot statement: "Phase 4 GREEN at {sha}; ready for Phase 5"
- Any legitimate SKIP/xfail patterns observed in the captured log
</output>
