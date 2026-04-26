---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 07
type: execute
wave: 1
depends_on: []
gap_closure: true
autonomous: true
requirements: [DECIDE-03]
files_modified:
  - python/src/boros_brain/decision/breakers/maturity.py
  - python/tests/test_breaker_maturity.py
  - docs/architecture.yml
  - docs/ARCHITECTURE.md
  - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md"
  - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md"

user_setup: []

must_haves:
  truths:
    - "`scripts/no_hardcoded_cancel_cost_lint.py` exits 0 against the live tree (DECIDE-03 lint guard is GREEN)."
    - "`python/src/boros_brain/decision/breakers/maturity.py` contains no hardcoded `cancel_cost = <number>` literal — `cancel_cost` is sourced exclusively via `await self._gas_cache.cancel_cost_pendle(...)`."
    - "`MaturityBreaker.__init__` requires `gas_cache` (positional) — there is no `gas_cache=None` default; production and test code paths both inject a `cancel_cost_pendle`-providing object."
    - "`python/tests/test_breaker_maturity.py` constructs a fake `GasHistoryCache` returning 0.0 and passes it to `MaturityBreaker(...)`; all 3 test cases pass."
    - "`docs/architecture.yml` declares the edge `brain.decision.breakers.maturity → brain.decision.gas_history` (type: calls) — currently absent in the Wave 2C edge block."
    - "`scripts/architecture_lint.py` exits 0 (no drift between source tree and `architecture.yml`)."
    - "Wiki `breaker-maturity-migration.md` Gas-Cache section is rewritten to reflect the mandatory-injection contract and supersedes the prior 'tests pass gas_cache=None' claim; Status remains `Current`."
    - "Wiki `gas-history-ewma-cancel-cost.md` exists with `Status: Current` and is the canonical reference for DECIDE-03 cancel-cost flow (referenced by the lint script's docstring)."
  artifacts:
    - path: "python/src/boros_brain/decision/breakers/maturity.py"
      provides: "SAFE-07 maturity breaker — gas_cache mandatory, no hardcoded cancel_cost"
      contains: "await self._gas_cache.cancel_cost_pendle"
    - path: "python/tests/test_breaker_maturity.py"
      provides: "3 GREEN tests using a fake gas_cache stub instead of None"
      contains: "_FakeGasCache"
    - path: "docs/architecture.yml"
      provides: "Phase 4 Wave 2C edge addition: maturity → gas_history (calls)"
      contains: "brain.decision.breakers.maturity"
    - path: "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md"
      provides: "Canonical DECIDE-03 cancel-cost flow page"
      contains: "Status:"
  key_links:
    - from: "python/src/boros_brain/decision/breakers/maturity.py"
      to: "python/src/boros_brain/decision/gas_history.py"
      via: "await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)"
      pattern: "self._gas_cache.cancel_cost_pendle"
    - from: "python/tests/test_breaker_maturity.py"
      to: "python/src/boros_brain/decision/breakers/maturity.py"
      via: "MaturityBreaker(gas_cache=_FakeGasCache())"
      pattern: "_FakeGasCache"
    - from: "docs/architecture.yml"
      to: "python/src/boros_brain/decision/breakers/maturity.py"
      via: "edge declaration brain.decision.breakers.maturity → brain.decision.gas_history"
      pattern: "brain.decision.breakers.maturity, to: brain.decision.gas_history"
---

<objective>
Close VERIFICATION.md Gap #1 — the DECIDE-03 lint guard (`scripts/no_hardcoded_cancel_cost_lint.py`) currently EXITS 1 because `python/src/boros_brain/decision/breakers/maturity.py:95` contains the literal `cancel_cost = 0.0  # test path (gas_cache=None)`. This violates the DECIDE-03 invariant ("cancel_cost sourced from gas_history.GasHistoryCache only — no hardcoded scalars in decision/") and means Roadmap Success Criterion #4 ("a stubbed-hardcoded value fails a linter check") is not actually green-lit on the live tree.

Resolution path (a) from VERIFICATION.md is preferred and used here: refactor MaturityBreaker so the test path injects a fake GasHistoryCache returning 0.0, removing the literal from production code. This honors the dependency-injection pattern that 04-06 already wired through the BreakerCoordinator (`MaturityBreaker(gas_cache=gas_cache)` at main.py:221) and keeps the lint authoritative for future regressions.

The change is small but architecturally meaningful: the maturity breaker's edge to gas_history goes from optional ("if self._gas_cache is not None") to mandatory ("await self._gas_cache.cancel_cost_pendle"), so `docs/architecture.yml` must declare the edge (it currently doesn't — Wave 2C edge block ends at line 2635 with only Wave 2A edges; the breakers→config-knob and the maturity→gas_history edges were never added). Engineering Protocol #2 requires the diagram update lands in the same commit as the source change.

Engineering Protocol #1 requires wiki updates: the `breaker-maturity-migration.md` page currently says "Tests pass gas_cache=None which causes cancel_cost to default to 0.0" — that statement is now historical and must be superseded. A new `gas-history-ewma-cancel-cost.md` page is created as the canonical DECIDE-03 reference (the lint script docstring already cites `[[gas-history-ewma-cancel-cost]]` but no such page existed — small protocol debt closed here).

Atomic-commit constraint: source change + tests + architecture.yml + ARCHITECTURE.md + wiki updates land in ONE commit. The pre-commit hook `scripts/architecture_lint.py` would fail a commit that touches `python/` without the YAML update.

Purpose: Make the DECIDE-03 lint authoritative against the live tree; close the Phase 4 verification gap; pivot Phase 4 to fully-shippable status.

Output: Refactored MaturityBreaker (gas_cache required), updated tests using a fake GasHistoryCache stub, architecture.yml + ARCHITECTURE.md reflecting the maturity→gas_history edge, and 2 wiki pages with Status fields. After this plan, `python3 scripts/no_hardcoded_cancel_cost_lint.py` and `python3 scripts/architecture_lint.py` both exit 0 against HEAD.
</objective>

<execution_context>
@$HOME/.claude-personal-personal/get-shit-done/workflows/execute-plan.md
@$HOME/.claude-personal-personal/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@CLAUDE.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-VERIFICATION.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md

# Source files for this refactor
@python/src/boros_brain/decision/breakers/maturity.py
@python/src/boros_brain/decision/gas_history.py
@python/src/boros_brain/decision/breaker_coordinator.py
@python/src/boros_brain/main.py
@python/tests/test_breaker_maturity.py

# Lint scripts whose green state this plan restores
@scripts/no_hardcoded_cancel_cost_lint.py
@scripts/architecture_lint.py

# Wiki pages this plan supersedes / creates
# (read with the Read tool — paths contain spaces, must be absolute)
# /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md

<interfaces>
<!-- Key contracts the executor needs. Read these first; do not re-derive. -->

From python/src/boros_brain/decision/gas_history.py:
```python
class GasHistoryCache:
    async def cancel_cost_pendle(self, *, w3, config: BotConfig) -> float:
        ...
```

From python/src/boros_brain/decision/breakers/base.py (Breaker ABC):
```python
class Breaker(Protocol):
    name: str
    async def check(self, *, sqlite_path: Path, w3: Any, parquet_root: Path,
                    config: Any, current_chain_ts: int) -> BreakerSignal: ...
```

From python/src/boros_brain/decision/breakers/maturity.py (current — to be refactored):
```python
class MaturityBreaker(Breaker):
    name = "maturity"
    def __init__(self, gas_cache: Any = None) -> None:
        self._gas_cache = gas_cache
    async def check(self, *, sqlite_path, w3, parquet_root, config,
                    current_chain_ts, last_r_me_pendle: float | None = None) -> BreakerSignal:
        # ... lines 92-95 contain the offending branch:
        # if self._gas_cache is not None and w3 is not None:
        #     cancel_cost = await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)
        # else:
        #     cancel_cost = 0.0  # test path (gas_cache=None)
```

From python/src/boros_brain/main.py:221 (production instantiation — already passes gas_cache):
```python
MaturityBreaker(gas_cache=gas_cache),
```

From scripts/no_hardcoded_cancel_cost_lint.py:61 (the regex that fails):
```python
PATTERN = re.compile(r"\bcancel_cost(?:_pendle)?\s*=\s*\d+\.?\d*")
```
The regex matches `cancel_cost = 0.0` but does NOT match `cancel_cost = await ...` or `cancel_cost = self._fallback_constant` (no digits after `=`).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Refactor MaturityBreaker — make gas_cache mandatory, remove the 0.0 literal, update tests with a fake gas_cache stub</name>
  <files>python/src/boros_brain/decision/breakers/maturity.py, python/tests/test_breaker_maturity.py</files>
  <read_first>
    - python/src/boros_brain/decision/breakers/maturity.py (the file being refactored — every line)
    - python/src/boros_brain/decision/gas_history.py (confirm `cancel_cost_pendle` signature and async-ness)
    - python/src/boros_brain/decision/breaker_coordinator.py (lines 56-76 — confirm coordinator passes a real gas_cache, so removing the None branch is safe in production)
    - python/src/boros_brain/main.py (lines 200-230 — confirm `MaturityBreaker(gas_cache=gas_cache)` is the only production construction site)
    - python/tests/test_breaker_maturity.py (the 3 tests calling `MaturityBreaker()` with no gas_cache that need updating)
    - scripts/no_hardcoded_cancel_cost_lint.py (the lint script — confirm what the regex matches and what it does NOT match)
    - python/src/boros_brain/decision/breakers/competition.py (precedent for a breaker with optional injected cache — pattern reference, do not modify)
  </read_first>
  <behavior>
    Test 1 (existing — `test_fires_when_remaining_below_migration_cost`): with maturity 1h away + last_r_me_pendle=0.001 + entrance_fee_pendle=0.5 + cancel_cost=0.0 → tripped=True, kill_command_kind="ROLL_POSITION".
    Test 2 (existing — `test_silent_when_remaining_above_migration_cost`): with maturity 30d away + last_r_me_pendle=10.0 + entrance_fee_pendle=0.5 + cancel_cost=0.0 → tripped=False.
    Test 3 (existing — `test_no_decision_history_yet`): with no last_r_me_pendle injected and no decisions rows → tripped=False, reason="no_decision_history_yet".
    All 3 must continue to pass after the refactor — the only change is HOW cancel_cost arrives (via a `_FakeGasCache` stub instead of the None-branch fallback).
    No new behaviors; this is a pure refactor preserving the existing semantics. The fake gas_cache returns 0.0 unconditionally so the tests' migration_cost arithmetic (entrance_fee_pendle + 2*0.0 = entrance_fee_pendle * buffer_pct) is identical to before.
  </behavior>
  <action>
**Sub-step 1A — refactor `python/src/boros_brain/decision/breakers/maturity.py`:**

a. In `__init__` (currently line 50), drop the `= None` default. New signature:
   ```python
   def __init__(self, gas_cache: Any) -> None:
       self._gas_cache = gas_cache
   ```
   Note: parameter is positional-or-keyword (matches `MaturityBreaker(gas_cache=gas_cache)` call site in main.py:221 — no caller change needed).

b. In `check()`, replace the entire branch at lines 92-95:
   ```python
   # OLD (lines 92-95):
   if self._gas_cache is not None and w3 is not None:
       cancel_cost = await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)
   else:
       cancel_cost = 0.0  # test path (gas_cache=None)
   ```
   With:
   ```python
   # NEW: cancel_cost is sourced unconditionally from the injected gas cache
   # (DECIDE-03 invariant — gas_history.GasHistoryCache is the single source).
   # Tests inject a fake gas_cache returning 0.0; production injects the real
   # GasHistoryCache instance via BreakerCoordinator (see main.py:221).
   cancel_cost = await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)
   ```
   Note: `w3` may still be None in tests. The fake gas_cache must accept `w3=None` without raising. The real GasHistoryCache uses `w3` to call `eth_feeHistory` — that path is exercised in production, not in tests.

c. Update the module docstring (lines 1-25) and class docstring (lines 38-46) to remove the "Tests pass gas_cache=None" language. Replace with: "gas_cache is dependency-injected (mandatory) by the BreakerCoordinator in production and by a fake stub in tests. The DECIDE-03 invariant requires cancel_cost to flow exclusively from gas_history.GasHistoryCache." Keep the `[[breaker-maturity-migration]]`, `[[boros-fee-schedule]]`, `[[circuit-breakers-v05]]` wiki citations. Add a new citation: `[[gas-history-ewma-cancel-cost]]: DECIDE-03 cancel-cost flow / GasHistoryCache contract`.

**Sub-step 1B — update `python/tests/test_breaker_maturity.py`:**

a. Add a module-level fake gas_cache stub near the top of the file (after the `_MARKET_DICT` constant, before `_config_with_market`):
   ```python
   class _FakeGasCache:
       """Test stub for MaturityBreaker.gas_cache.

       Returns 0.0 from cancel_cost_pendle unconditionally — equivalent to the
       old `gas_cache=None` test path that was removed by Plan 04-07 to satisfy
       the DECIDE-03 lint (no hardcoded cancel_cost literals in decision/).
       """
       async def cancel_cost_pendle(self, *, w3, config) -> float:
           return 0.0
   ```

b. Update each of the 3 test cases (lines 72, 106, 134):
   ```python
   # OLD:  breaker = MaturityBreaker()
   # NEW:  breaker = MaturityBreaker(gas_cache=_FakeGasCache())
   ```
   No other test logic changes; the keyword `w3=None` already passed to `check()` is fine because the fake doesn't dereference w3.

c. Update the test file's module docstring (lines 1-13) to reflect: "Tests inject a `_FakeGasCache` returning 0.0 cancel_cost; the gas_cache parameter is mandatory after Plan 04-07."

**Sub-step 1C — verify locally:**

Run the lint and the 3 tests inline at the end of this task (executor: include the actual command output in your task summary):

```bash
python3 scripts/no_hardcoded_cancel_cost_lint.py; echo "lint exit: $?"
cd python && uv run python -m pytest tests/test_breaker_maturity.py -q
```

Both must succeed before continuing to Task 2.
  </action>
  <verify>
    <automated>python3 scripts/no_hardcoded_cancel_cost_lint.py</automated>
    <automated>cd python && uv run python -m pytest tests/test_breaker_maturity.py -q --tb=short</automated>
    <automated>! grep -nE '\bcancel_cost(_pendle)?\s*=\s*[0-9]' python/src/boros_brain/decision/breakers/maturity.py</automated>
    <automated>grep -q 'await self._gas_cache.cancel_cost_pendle' python/src/boros_brain/decision/breakers/maturity.py</automated>
    <automated>grep -q '_FakeGasCache' python/tests/test_breaker_maturity.py</automated>
    <automated>! grep -q 'gas_cache: Any = None' python/src/boros_brain/decision/breakers/maturity.py</automated>
  </verify>
  <acceptance_criteria>
    - `python3 scripts/no_hardcoded_cancel_cost_lint.py` exits 0 (no output to stderr).
    - `cd python && uv run python -m pytest tests/test_breaker_maturity.py -q` exits 0; all 3 tests in that file PASS.
    - `grep -n 'cancel_cost = 0.0' python/src/boros_brain/decision/breakers/maturity.py` returns no matches.
    - `grep -nE '\bcancel_cost(_pendle)?\s*=\s*[0-9]' python/src/boros_brain/decision/breakers/maturity.py` returns no matches.
    - `grep -n 'await self._gas_cache.cancel_cost_pendle' python/src/boros_brain/decision/breakers/maturity.py` returns at least one match.
    - `grep -n 'gas_cache: Any = None' python/src/boros_brain/decision/breakers/maturity.py` returns no matches (default removed).
    - `grep -n 'class _FakeGasCache' python/tests/test_breaker_maturity.py` returns exactly one match.
    - `grep -cn 'MaturityBreaker(gas_cache=_FakeGasCache())' python/tests/test_breaker_maturity.py` returns 3 (the 3 test cases).
  </acceptance_criteria>
  <done>
    The DECIDE-03 lint is GREEN against the live tree, the 3 maturity-breaker tests are GREEN, and the production code path uses the injected gas_cache unconditionally with no test-path-only branch.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update docs/architecture.yml + docs/ARCHITECTURE.md to declare the maturity → gas_history edge (Engineering Protocol #2)</name>
  <files>docs/architecture.yml, docs/ARCHITECTURE.md</files>
  <read_first>
    - docs/architecture.yml (lines 1340-1395 for Wave 2C nodes; lines 2612-2636 for Wave 2A edges — confirm the Wave 2C/3 edge block is missing the `breakers.maturity → gas_history` edge)
    - docs/ARCHITECTURE.md (the Mermaid diagram — find the Phase 4 subgraph and the maturity node)
    - scripts/architecture_lint.py (read the relevant scan strategy — confirms it parses both Mermaid and YAML)
    - python/src/boros_brain/decision/breakers/maturity.py (post-Task-1 state — confirms the new edge exists in code)
    - python/src/boros_brain/decision/gas_history.py (target node identifier `brain.decision.gas_history`)
  </read_first>
  <action>
**Sub-step 2A — append the missing edge to `docs/architecture.yml`:**

The current Wave 2A edge block ends at line 2635 (`config.pricing.pendle_price_usd, type: depends-on-config`). The Wave 2C and Wave 3 edge block appears to have never been written. Append a new section after the existing Wave 2A block (before EOF — file currently ends at line 2636):

```yaml

  # ── Phase 4 Wave 2C breakers.maturity edge — Plan 04-07 (gap closure) ─────
  # MaturityBreaker now requires the injected GasHistoryCache (no None default).
  # The DECIDE-03 invariant — cancel_cost flows exclusively through GasHistoryCache —
  # is now enforced by the production code path (no test-only fallback branch).
  - {from: brain.decision.breakers.maturity, to: brain.decision.gas_history, type: calls, notes: "SAFE-07 migration_cost = entrance_fee_pendle + 2 × cancel_cost_pendle; cancel_cost_pendle returned by injected GasHistoryCache (Plan 04-07 made gas_cache mandatory)"}
```

If, after reading architecture.yml, you find that other Wave 2C/3 edges DO exist (i.e., the file is longer than the 2636 lines I observed and the Wave 2A block is followed by additional Phase 4 blocks that the verifier didn't surface), then append the maturity→gas_history edge to whichever existing block is most semantically appropriate (likely a Wave 2C breakers block) — preserve the comment header style (`# ── Phase 4 Wave 2C ... ─`) and add the same edge entry shown above. Do NOT duplicate edges.

After the edit, run `python3 -c "import yaml; yaml.safe_load(open('docs/architecture.yml'))"` and confirm exit 0 — proves the YAML still parses.

**Sub-step 2B — update `docs/ARCHITECTURE.md` Mermaid diagram:**

Find the Phase 4 subgraph (search for `breakers.maturity` or `decision/breakers/maturity`). Add a new arrow from `breakers.maturity` to `gas_history` with the label `calls` (or whatever convention the existing Phase 4 edges use — match the surrounding style: e.g., `breakers.maturity --> gas_history`). If the diagram does not yet have the `breakers.maturity` node rendered, add it inside the Phase 4 subgraph with the same node-style as siblings (e.g., `clo_shift`, `oracle_stale`).

If the Mermaid diagram doesn't have a per-edge view of breakers (some projects use a coarse "all breakers → coordinator" depiction), then the YAML edge addition is sufficient — note this in the SUMMARY and proceed. Architecture-lint runs against the YAML, not the Mermaid.

**Sub-step 2C — verify drift is closed:**

```bash
python3 scripts/architecture_lint.py
echo "architecture_lint exit: $?"
```

Must exit 0. If it errors with "undeclared edge" pointing at maturity → gas_history, the YAML addition is correct but the executor missed it; re-check the indentation under `edges:`.

If the lint errors with anything else (e.g., a pre-existing drift in some other module), STOP — that's a separate gap. File a note in the task SUMMARY ("architecture_lint reports unrelated drift in <module> — not part of this plan, surfaced for follow-up") but do not attempt to fix it here.
  </action>
  <verify>
    <automated>python3 scripts/architecture_lint.py</automated>
    <automated>python3 -c "import yaml; yaml.safe_load(open('docs/architecture.yml'))"</automated>
    <automated>grep -q 'brain.decision.breakers.maturity, to: brain.decision.gas_history' docs/architecture.yml</automated>
  </verify>
  <acceptance_criteria>
    - `python3 scripts/architecture_lint.py` exits 0 (no drift between source tree and YAML).
    - `python3 -c "import yaml; yaml.safe_load(open('docs/architecture.yml'))"` exits 0 (YAML still parses).
    - `grep -nE 'brain\.decision\.breakers\.maturity.*brain\.decision\.gas_history' docs/architecture.yml` returns at least one match (the new edge declaration).
    - `docs/ARCHITECTURE.md` either shows the new edge OR the executor's SUMMARY documents that the Mermaid is at coarse granularity (and architecture_lint, which scans the YAML, is the authoritative gate).
  </acceptance_criteria>
  <done>
    Engineering Protocol #2 is satisfied: the architecture YAML declares every code-level dependency edge and `architecture_lint` exits 0. The maturity → gas_history edge is now visible to anyone tracing the SAFE-07 dependency graph.
  </done>
</task>

<task type="auto">
  <name>Task 3: Update LLM Wiki — supersede the breaker-maturity-migration "gas_cache=None" claim and create gas-history-ewma-cancel-cost canonical page (Engineering Protocol #1)</name>
  <files>
    /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md,
    /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md
  </files>
  <read_first>
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md (the page to update — see "Gas Cache Dependency Injection" section, currently claims tests pass gas_cache=None)
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md (to add the new page to the wiki index if needed)
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/circuit-breakers-v05.md (style/format reference for breaker pages; do NOT modify)
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/fee-schedule.md (style/format reference; do NOT modify)
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/CLAUDE.md (read-only — wiki tooling contract for Status field, kebab-case filenames, supersedence pattern)
    - python/src/boros_brain/decision/gas_history.py (for the canonical contract description in the new page)
  </read_first>
  <action>
**Sub-step 3A — update `breaker-maturity-migration.md`:**

Replace the "## Gas Cache Dependency Injection" section (currently lines ~39-41) with:

```markdown
## Gas Cache Dependency Injection

`cancel_cost_pendle` is obtained via the injected `gas_cache` object. As of Plan 04-07 (2026-04-25), the `gas_cache` parameter is **mandatory** — `MaturityBreaker.__init__(gas_cache=...)` has no default. Production code instantiates with the real `GasHistoryCache` (see `main.py`); tests inject a `_FakeGasCache` stub returning 0.0 (see `python/tests/test_breaker_maturity.py`). The DECIDE-03 invariant — cancel_cost flows exclusively through GasHistoryCache — is enforced by the lint script `scripts/no_hardcoded_cancel_cost_lint.py`.

See [[gas-history-ewma-cancel-cost]] for the canonical cancel-cost flow.

**Historical note (superseded 2026-04-25):** Prior to Plan 04-07, this page documented "Tests pass `gas_cache=None` which causes cancel_cost to default to 0.0." That code path was removed because the literal `cancel_cost = 0.0` failed the DECIDE-03 lint guard against the live tree (VERIFICATION.md gap #1).
```

Keep the `**Status:** Current` line at the top of the page unchanged (the page is current — only the Gas Cache section is being rewritten with a supersedence note). If the page does not already have a `**Status:**` line on a separate line near the top, add it: `**Status:** Current`.

**Sub-step 3B — create `gas-history-ewma-cancel-cost.md`:**

This page is referenced by `scripts/no_hardcoded_cancel_cost_lint.py` (lines 4-7 of its docstring) as `[[gas-history-ewma-cancel-cost]]` — the wiki link existed in code but the page itself was never filed. Plan 04-07 closes that protocol debt. Create:

```markdown
# Gas History EWMA — Cancel Cost (DECIDE-03)

**Status:** Current

The single authoritative source of `cancel_cost_pendle` for the EV cancel rule (DECIDE-01) and the SAFE-07 maturity migration cost. Computed from live Arbitrum `eth_feeHistory` reads via an exponentially-weighted moving average over the configured block window.

## Module

`python/src/boros_brain/decision/gas_history.py` — class `GasHistoryCache`.

```python
async def cancel_cost_pendle(self, *, w3, config: BotConfig) -> float:
    """Return the current cancel_cost in PENDLE units."""
```

## Computation

`cancel_cost_pendle` = `cancel_gas_units_estimate × ewma_gwei × 1e-9 × eth_price_usd / pendle_price_usd`

EWMA decay: `α` per `BotConfig.decision.cancel_cost_ewma_alpha` (per-block).
Block window: `BotConfig.decision.cancel_cost_block_window` blocks per refresh.
TTL: `BotConfig.decision.cancel_cost_ttl_s` seconds before re-fetch.

## DECIDE-03 Invariant

No file under `python/src/boros_brain/decision/` may assign a hardcoded `cancel_cost = <number>` literal. The pre-commit hook `scripts/no_hardcoded_cancel_cost_lint.py` enforces this. The only file allowed to bind `cancel_cost`-named variables to non-await expressions is `gas_history.py` itself (allowlisted).

PITFALLS §C5 motivation: a stale literal defeats the EV calculation and can cause the strategy to hold orders when cancellation is actually cheap (or to cancel when it's expensive).

## Consumers

- `decision/engine.py` — EV cancel rule (DECIDE-01) `cancel_cost = await gas_cache.cancel_cost_pendle(...)`
- `decision/breakers/maturity.py` — SAFE-07 migration_cost arithmetic (made mandatory in Plan 04-07)

## Dependency Injection Pattern

`GasHistoryCache` is instantiated once at boot in `main.py` and passed by reference to:
- The decision engine via the `_decision_loop` closure.
- The `BreakerCoordinator(gas_cache=...)` constructor, which forwards it to `MaturityBreaker(gas_cache=...)`.

Tests inject a fake stub (e.g., `_FakeGasCache` in `test_breaker_maturity.py`) returning a fixed value. The fake's signature must match `cancel_cost_pendle(*, w3, config)` and return a `float`.

## Related

- [[ev-cancel-rule]] — DECIDE-01/02 EV equation
- [[breaker-maturity-migration]] — SAFE-07 consumer of cancel_cost
- [[fee-schedule]] — Boros fee schedule reference
```

**Sub-step 3C — wire the new page into the wiki index:**

Read `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md`. If it has a categorized list (e.g., a "Decision Engine" or "Breakers" or "Phase 4" section), add a bullet `- [[gas-history-ewma-cancel-cost]] — DECIDE-03 cancel_cost flow + GasHistoryCache contract` in the appropriate section. If the index uses a flat alphabetical layout, insert in the alphabetical position.

If the index format is not obvious or the page would only be inserted in one place, use minimal-disruption editing — a single insert is enough; do not refactor the index file structure.

**Sub-step 3D — run the LLM Wiki linter (if available) on the boros workspace:**

```bash
cd "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki" && python -m src.lint.lint_engine -w boros --no-external 2>&1 | head -20
```

If the linter is not installed in this venv (ImportError), skip with a note in the task SUMMARY — the wiki linter is operator-tooling; the source-of-truth is the page Status fields and content correctness. If the linter runs and reports issues other than the new pages (pre-existing drift), document but do not fix here.
  </action>
  <verify>
    <automated>test -f "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md"</automated>
    <automated>grep -q '^\*\*Status:\*\* Current' "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md"</automated>
    <automated>grep -q 'gas_cache.*mandatory' "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md"</automated>
    <automated>grep -q 'Historical note (superseded 2026-04-25)' "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md"</automated>
    <automated>grep -q 'gas-history-ewma-cancel-cost' "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md"</automated>
  </verify>
  <acceptance_criteria>
    - File `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md` exists.
    - The new page has `**Status:** Current` at the top.
    - `breaker-maturity-migration.md` Gas Cache section is rewritten — `grep -q 'gas_cache.*mandatory'` returns at least one match AND `grep -q 'Historical note (superseded 2026-04-25)'` returns at least one match.
    - `breaker-maturity-migration.md` cross-references `[[gas-history-ewma-cancel-cost]]`.
    - The wiki index references the new page (manual check; the executor's SUMMARY confirms the insertion location).
  </acceptance_criteria>
  <done>
    Engineering Protocol #1 is satisfied: the wiki page that the lint script docstring referenced now exists, and the prior breaker-maturity claim about `gas_cache=None` is explicitly superseded with date and reason. Future readers tracing DECIDE-03 will land on the canonical page; future maintainers reading breaker-maturity-migration will see the supersedence note.
  </done>
</task>

<task type="auto">
  <name>Task 4: Atomic commit — production code + tests + architecture YAML/MD + wiki, then re-run all gates and confirm Phase 4 verification gap is closed</name>
  <files>(no new files — git commit + verification only)</files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VERIFICATION.md (the gap source — confirm Gap #1 is the only blocker)
    - CLAUDE.md (commit hygiene rules — single atomic commit; pre-commit hook expects YAML + Mermaid + code together)
  </read_first>
  <action>
**Sub-step 4A — verify the changeset before committing:**

Confirm the diff is exactly what we expect — no surprises:

```bash
git status
git diff --stat
```

Expected files in the diff (no others outside .planning/ which is for the SUMMARY):
- `python/src/boros_brain/decision/breakers/maturity.py`
- `python/tests/test_breaker_maturity.py`
- `docs/architecture.yml`
- `docs/ARCHITECTURE.md`  *(or, if the Mermaid wasn't fine-grained enough to need a touch, this file may be unchanged — that's acceptable per Task 2's note)*
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md`
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md`
- (potentially) `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md`

NOTE: the LLM Wiki lives under a different repo (`/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/`) — those files are tracked by THAT repo's git, not boros. From the boros repo's perspective the wiki edits are external and do not appear in `git status`. That's fine; the wiki repo has its own commit discipline. Only commit boros-repo files in this step. The wiki repo commit is a separate operation handled per the LLM Wiki tooling contract.

**Sub-step 4B — run the full gate suite locally before commit:**

```bash
python3 scripts/no_hardcoded_cancel_cost_lint.py; echo "no_hardcoded_cancel_cost: $?"
python3 scripts/no_threshold_dials_lint.py; echo "no_threshold_dials: $?"
python3 scripts/architecture_lint.py; echo "architecture_lint: $?"
python3 scripts/sqlite_writer_lint.py; echo "sqlite_writer: $?"
cd python && uv run python -m pytest tests/test_breaker_maturity.py -q --tb=short
```

ALL must exit 0 / GREEN. If any lint other than `architecture_lint` is failing, that's a regression — STOP and inspect the diff.

**Sub-step 4C — atomic commit:**

```bash
git add \
  python/src/boros_brain/decision/breakers/maturity.py \
  python/tests/test_breaker_maturity.py \
  docs/architecture.yml \
  docs/ARCHITECTURE.md
# Note: `git add docs/ARCHITECTURE.md` is harmless if unchanged.

git commit -m "$(cat <<'EOF'
fix(04-07): make MaturityBreaker.gas_cache mandatory — close DECIDE-03 lint gap

VERIFICATION.md flagged that scripts/no_hardcoded_cancel_cost_lint.py exits 1
because decision/breakers/maturity.py:95 contained `cancel_cost = 0.0` as a
test-path fallback. The DECIDE-03 invariant (cancel_cost sourced exclusively
from gas_history.GasHistoryCache) was therefore violated on the live tree.

This commit refactors MaturityBreaker to require gas_cache as a mandatory
positional argument; the test suite injects a _FakeGasCache stub returning
0.0 instead. Production code (BreakerCoordinator at main.py:221) was already
passing a real GasHistoryCache, so no production wiring change.

Architecture YAML updated: brain.decision.breakers.maturity → gas_history
edge declared (was missing — Wave 2C edge block was incomplete).

Wiki:
- breaker-maturity-migration.md: gas_cache=None claim superseded
- gas-history-ewma-cancel-cost.md: created (canonical DECIDE-03 reference,
  was referenced by lint docstring but never filed)
- (wiki commits land separately in the LLM Wiki repo)

Closes Phase 4 VERIFICATION.md Gap #1.
EOF
)"
```

The pre-commit hook `scripts/architecture_lint.py` and `scripts/no_hardcoded_cancel_cost_lint.py` will run automatically. If they fail, do NOT use `--no-verify` — investigate and fix. The point of these hooks is to catch exactly this class of regression.

If the commit succeeds, capture the commit hash:
```bash
git log -1 --pretty=oneline
```

**Sub-step 4D — post-commit verification (mirrors VERIFICATION.md gap criterion):**

```bash
python3 scripts/no_hardcoded_cancel_cost_lint.py
echo "post-commit lint exit: $?"
```

This must exit 0 against HEAD. If it does, Gap #1 from VERIFICATION.md is closed.

Document the commit hash and the lint output in the plan SUMMARY's Evidence section.
  </action>
  <verify>
    <automated>python3 scripts/no_hardcoded_cancel_cost_lint.py</automated>
    <automated>python3 scripts/architecture_lint.py</automated>
    <automated>python3 scripts/no_threshold_dials_lint.py</automated>
    <automated>cd python && uv run python -m pytest tests/test_breaker_maturity.py -q --tb=short</automated>
    <automated>git log -1 --format='%s' | grep -q '04-07'</automated>
  </verify>
  <acceptance_criteria>
    - `python3 scripts/no_hardcoded_cancel_cost_lint.py` exits 0 against HEAD (the gap is closed).
    - `python3 scripts/architecture_lint.py` exits 0 against HEAD (no drift).
    - `python3 scripts/no_threshold_dials_lint.py` exits 0 against HEAD (no DECIDE-04 regression).
    - `cd python && uv run python -m pytest tests/test_breaker_maturity.py -q` exits 0 (no test regression).
    - The commit landed cleanly via the pre-commit hooks (no `--no-verify` was used).
    - `git log -1 --format=%s` contains the substring `04-07`.
    - Plan SUMMARY records the commit hash and the exit-0 status of all four lint/test commands as Evidence, explicitly citing VERIFICATION.md Gap #1 as closed.
  </acceptance_criteria>
  <done>
    Phase 4 VERIFICATION.md Gap #1 is closed; the DECIDE-03 lint guard is GREEN against the live tree; the architectural delta + wiki updates landed atomically. Phase 4 is now ready for the operator-runnable end-to-end test pass (Plan 04-08).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

This refactor introduces no new trust boundaries. The change is internal: an existing dependency-injection pattern (gas_cache passed by BreakerCoordinator to MaturityBreaker) is made mandatory at the type level. No new external inputs, no new network surfaces, no new IPC channels.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-07-01 | Tampering | `MaturityBreaker.cancel_cost` source | mitigate | DECIDE-03 lint (`scripts/no_hardcoded_cancel_cost_lint.py`) is now GREEN against the live tree — any future PR introducing a hardcoded `cancel_cost` literal in `decision/` will fail pre-commit. The maturity refactor closes the bypass that previously allowed the literal in production code. |
| T-04-07-02 | (none) | (refactor scope) | accept | No new external inputs, trust boundaries, or attack surface — change is internal refactor of an existing dependency-injection pattern. The fake gas_cache used in tests is process-local and never crosses a trust boundary. |
</threat_model>

<verification>
After Task 4:
- `python3 scripts/no_hardcoded_cancel_cost_lint.py` → exit 0 (DECIDE-03 lint GREEN)
- `python3 scripts/architecture_lint.py` → exit 0 (no drift)
- `python3 scripts/no_threshold_dials_lint.py` → exit 0 (no DECIDE-04 regression)
- `cd python && uv run python -m pytest tests/test_breaker_maturity.py -q` → exit 0 (3 tests GREEN)
- The atomic commit landed without `--no-verify`.
- VERIFICATION.md Gap #1 status flips from FAILED to VERIFIED.
</verification>

<success_criteria>
1. **Lint:** `python3 scripts/no_hardcoded_cancel_cost_lint.py` exits 0 against HEAD.
2. **Architecture:** `python3 scripts/architecture_lint.py` exits 0; YAML declares `brain.decision.breakers.maturity → brain.decision.gas_history` edge.
3. **Tests:** All 3 tests in `python/tests/test_breaker_maturity.py` pass; they construct a `_FakeGasCache` stub instead of `None`.
4. **Source:** `python/src/boros_brain/decision/breakers/maturity.py` contains `await self._gas_cache.cancel_cost_pendle(...)` and contains zero `cancel_cost = <digit>` literals; `__init__` requires `gas_cache` (no default).
5. **Wiki:** `breaker-maturity-migration.md` Gas Cache section is rewritten with a supersedence note; `gas-history-ewma-cancel-cost.md` exists as the canonical DECIDE-03 reference page.
6. **Atomic commit:** All boros-repo files land in a single commit via pre-commit hooks (no `--no-verify`).
7. **Gap closed:** Phase 4 VERIFICATION.md Gap #1 is resolvable as VERIFIED on re-run.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-07-maturity-breaker-cancel-cost-injection-refactor-SUMMARY.md` documenting:
- Commit hash of the atomic commit
- Output of `python3 scripts/no_hardcoded_cancel_cost_lint.py` (exit 0)
- Output of `python3 scripts/architecture_lint.py` (exit 0)
- Output of `cd python && uv run python -m pytest tests/test_breaker_maturity.py -q` (3 PASSED)
- Confirmation that VERIFICATION.md Gap #1 is closed
- Path to the new wiki page (`gas-history-ewma-cancel-cost.md`) and confirmation that `breaker-maturity-migration.md` was updated with a supersedence note
- Any caveats (e.g., if the Mermaid diagram in `docs/ARCHITECTURE.md` did not need a fine-grained edit because Phase 4 is depicted at coarse granularity, document that explicitly).
</output>
