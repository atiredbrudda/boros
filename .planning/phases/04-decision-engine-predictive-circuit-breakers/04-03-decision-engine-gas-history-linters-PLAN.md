---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 03
type: execute
wave: 2
depends_on: [01, 02]
autonomous: true
requirements: [DECIDE-01, DECIDE-02, DECIDE-03, DECIDE-04]
files_modified:
  - python/src/boros_brain/decision/engine.py
  - python/src/boros_brain/decision/gas_history.py
  - scripts/no_hardcoded_cancel_cost_lint.py
  - scripts/no_threshold_dials_lint.py
  - python/tests/test_decision_engine_ev_equation.py
  - python/tests/test_decision_engine_voluntary_branch.py
  - python/tests/test_gas_history_ewma.py
  - python/tests/test_no_threshold_dials_lint.py
  - docs/architecture.yml
  - docs/ARCHITECTURE.md

user_setup: []

must_haves:
  truths:
    - "engine.evaluate() returns EvaluateOutput; cancels iff EV_hold < 0; voluntary_cancel_branch toggle works in both branches."
    - "GasHistoryCache.cancel_cost_pendle returns a wei->PENDLE EWMA over 100 Arbitrum blocks; cache TTL of 60s respected."
    - "no_hardcoded_cancel_cost_lint and no_threshold_dials_lint both PASS on Phase-4-final main; the test files for both linters PASS without xfail."
    - "Phase 4 RED tests for DECIDE-01..04 all turn GREEN."
    - "Engine + gas_history nodes registered in architecture.yml in same commit as the source files."
    - "Wiki pages [[ev-cancel-rule-implementation-v05]] and [[gas-history-ewma-cancel-cost]] filed with Status: Current."
  artifacts:
    - path: "python/src/boros_brain/decision/engine.py"
      provides: "async evaluate() implementing DECIDE-01/02 EV cancel rule"
      contains: "async def evaluate"
      min_lines: 80
    - path: "python/src/boros_brain/decision/gas_history.py"
      provides: "GasHistoryCache TTL+EWMA over eth_feeHistory"
      contains: "class GasHistoryCache"
      min_lines: 50
    - path: "scripts/no_hardcoded_cancel_cost_lint.py"
      provides: "DECIDE-03 enforcement (PASS on main; FAIL if a hardcoded scalar is reintroduced)"
      contains: "PROTECTED_DIRS"
    - path: "scripts/no_threshold_dials_lint.py"
      provides: "DECIDE-04 audit (PASS on main; FAIL if a non-breaker _threshold field appears)"
      contains: "ALLOWED_FILES"
  key_links:
    - from: "python/src/boros_brain/decision/engine.py"
      to: "python/src/boros_brain/fill_model/predict.py"
      via: "predict() call"
      pattern: "from .*fill_model.predict import predict"
    - from: "python/src/boros_brain/decision/engine.py"
      to: "python/src/boros_brain/loss_model/expected_loss.py"
      via: "expected_loss() call"
      pattern: "from .*loss_model.expected_loss import expected_loss"
    - from: "python/src/boros_brain/decision/engine.py"
      to: "python/src/boros_brain/reward_model/r_capped.py"
      via: "r_capped_curve() call"
      pattern: "from .*reward_model.r_capped import r_capped_curve"
    - from: "python/src/boros_brain/decision/gas_history.py"
      to: "external.arbitrum.fee_history"
      via: "AsyncWeb3.eth.fee_history call"
      pattern: "fee_history"
    - from: "scripts/no_hardcoded_cancel_cost_lint.py"
      to: "python/src/boros_brain/decision/gas_history.py"
      via: "ALLOWED_FILES allowlist (gas_history.py is the only legit owner)"
      pattern: "gas_history"
---

<objective>
Wave 2 plan A — turn the DECIDE-01..04 RED tests GREEN. Implement async engine.evaluate() that composes Phase 2 predict() + Phase 3 expected_loss() + r_capped_curve() + new gas_history.cancel_cost_pendle(), with the voluntary_cancel_forfeits_accumulated branch toggle. Tighten the two lint scripts (no_hardcoded_cancel_cost, no_threshold_dials) to enforce DECIDE-03 / DECIDE-04 invariants on the codebase.

Purpose: Lock the EV equation in code so Phase 5 backtest and Phase 7 paper trading consume an immutable, line-by-line-EV-sign-correct decision primitive. Lint scripts mechanically enforce that future contributors cannot reintroduce hardcoded cancel_cost or threshold dials.

Output: engine.py + gas_history.py source; 2 lint scripts hardened; architecture.yml engine + gas_history nodes; 4 RED tests turn GREEN; 2 wiki pages filed.
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
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-01-test-scaffolding-and-lint-stubs-PLAN.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-02-foundation-schema-migration-writers-PLAN.md
@CLAUDE.md
@python/src/boros_brain/fill_model/predict.py
@python/src/boros_brain/fill_model/schemas.py
@python/src/boros_brain/loss_model/expected_loss.py
@python/src/boros_brain/loss_model/schemas.py
@python/src/boros_brain/reward_model/r_capped.py
@python/src/boros_brain/reward_model/schemas.py
@python/src/boros_brain/data/chain_time.py
@python/src/boros_brain/decision/schemas.py
@python/src/boros_brain/decision/config.py
@scripts/no_time_time_lint.py
@scripts/no_hardcoded_cancel_cost_lint.py
@scripts/no_threshold_dials_lint.py

<interfaces>
From Phase 2 (already in main):
  def predict(req: PredictInput, *, sqlite_path: Path, config: BotConfig) -> PredictOutput
    raises FillModelStaleFeatureError, FillModelNoFreshFitError
    PredictOutput.p_fill_this_epoch, PredictOutput.fit_status

From Phase 3 (already in main):
  def expected_loss(req: ExpectedLossInput, *, sqlite_path: Path, config: BotConfig) -> ExpectedLossOutput
    raises LossModelNoFreshGridError
    ExpectedLossOutput.expected_loss_pendle, ExpectedLossOutput.fit_status

  def r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput
    RewardCurveOutput.r_capped_pendle, RewardCurveOutput.regime

From Phase 4 Plan 04-02 (foundation):
  EvaluateInput, EvaluateOutput  (decision/schemas.py)
  DecisionEngineConfig with cancel_cost_ewma_alpha=0.1, cancel_cost_ttl_s=60.0, cancel_cost_block_window=100
  ExecutionConfig.cancel_gas_units_estimate=200_000, ExecutionConfig.entrance_fee_pendle
  PricingConfig.eth_price_usd, PricingConfig.pendle_price_usd

From Phase 1 (already in main):
  async def chain_time.now_cached() -> int  (TTL-cached chain timestamp)
  AsyncWeb3 client (rpc_client.make_arbitrum_rpc) with .eth.fee_history(blockCount, newest_block, reward_percentiles)

NEW interfaces created in this plan:
  class GasHistoryCache:
    last_fetch_chain_ts: int = 0
    last_value_pendle: float = 0.0
    ewma_state: float = 0.0
    async def cancel_cost_pendle(self, *, w3, config: BotConfig) -> float

  async def evaluate(req: EvaluateInput, *, sqlite_path: Path, config: BotConfig,
                    gas_cache: GasHistoryCache, w3) -> EvaluateOutput
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: GasHistoryCache (DECIDE-03)</name>
  <files>
    python/src/boros_brain/decision/gas_history.py,
    python/tests/test_gas_history_ewma.py
  </files>
  <read_first>
    - python/src/boros_brain/data/chain_time.py (lines 76-180, ChainTimeCache TTL pattern — verbatim model)
    - python/src/boros_brain/data/rpc_client.py (AsyncWeb3 wrapper — w3.eth signature)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (DECIDE-03 §, lines 415-462)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (gas_history pattern lines 270-340)
    - python/src/boros_brain/decision/config.py (after Plan 04-02 — DecisionEngineConfig fields, ExecutionConfig.cancel_gas_units_estimate, PricingConfig.eth_price_usd / pendle_price_usd)
    - python/tests/test_gas_history_ewma.py (RED tests from 04-01 — must turn GREEN)
  </read_first>
  <behavior>
    GasHistoryCache:
      @dataclass
      class GasHistoryCache:
          last_fetch_chain_ts: int = 0
          last_value_pendle: float = 0.0
          ewma_state: float = field(default=0.0)

          async def cancel_cost_pendle(self, *, w3, config: BotConfig) -> float:
              now = await chain_time.now_cached()
              ttl = config.decision.cancel_cost_ttl_s
              if now - self.last_fetch_chain_ts < ttl and self.last_fetch_chain_ts != 0:
                  return self.last_value_pendle
              try:
                  hist = await asyncio.wait_for(
                      w3.eth.fee_history(config.decision.cancel_cost_block_window, "latest", [50]),
                      timeout=5.0,
                  )
              except (TimeoutError, Exception) as exc:
                  log.warning("gas_history.fetch_failed", err=str(exc),
                              last_value_pendle=self.last_value_pendle)
                  return self.last_value_pendle
              base_fees = list(hist["baseFeePerGas"][:-1])
              priority = [r[0] if r else 0 for r in hist.get("reward", [])]
              # pad priority with zeros to match base_fees length
              while len(priority) < len(base_fees):
                  priority.append(0)
              samples = [int(b) + int(p) for b, p in zip(base_fees, priority[:len(base_fees)])]
              alpha = config.decision.cancel_cost_ewma_alpha
              ewma = self.ewma_state if self.ewma_state else float(samples[0])
              for s in samples[1:]:
                  ewma = alpha * float(s) + (1 - alpha) * ewma
              self.ewma_state = ewma
              gas_units = config.execution.cancel_gas_units_estimate
              wei = ewma * gas_units
              eth = wei / 1e18
              usd = eth * config.pricing.eth_price_usd
              pendle = usd / config.pricing.pendle_price_usd
              self.last_value_pendle = float(pendle)
              self.last_fetch_chain_ts = int(now)
              return self.last_value_pendle

    The function MUST use chain_time.now_cached() — never time.time(). The module is under decision/ which is in no_time_time_lint PROTECTED_DIRS.

    Test changes — turn xfail/skip into pass:
    - test_ewma_correctness: with mocked fee_history returning baseFeePerGas of 100 wei for 100 entries plus reward of 10 wei, the wei value is 110, EWMA seeded with first sample = 110 then iterations stay at 110, total wei = 110 * 200_000 = 22_000_000, eth = 2.2e-11, usd = 6.6e-8 (with eth_price_usd=3000), pendle = 2.2e-8 (with pendle_price_usd=3.0). Use math.isclose with rel_tol=1e-3.
    - test_ttl_cache: AsyncMock w3 — call cancel_cost_pendle twice within ttl; assert mock.call_count == 1.
    - test_linter_catches_hardcoded: write a tmp .py file with `cancel_cost = 0.5` under decision/; invoke scripts.no_hardcoded_cancel_cost_lint.main(); assert exit code 1.
    - test_linter_passes_when_clean: invoke against actual decision/ dir AFTER engine.py + gas_history.py land (this task lands gas_history.py; Task 3 lands engine.py); assert exit code 0.
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/gas_history.py with the EXACT body from <behavior>. Header docstring cites [[gas-history-ewma-cancel-cost]] and DECIDE-03 with PITFALLS Phase-4 #5 reference. Imports:
   - from __future__ import annotations
   - import asyncio
   - from dataclasses import dataclass, field
   - import structlog
   - from ..config.schema import BotConfig
   - from ..data import chain_time
   - log = structlog.get_logger(__name__)
   - __all__ = ["GasHistoryCache"]

2. Update python/tests/test_gas_history_ewma.py:
   - Remove the importorskip guard (it now resolves successfully since gas_history.py exists)
   - Implement test_ewma_correctness with the exact mocked fee_history shape
   - Implement test_ttl_cache using AsyncMock and call_count assertion
   - Implement test_linter_catches_hardcoded with monkeypatch of PROTECTED_DIRS to a tmp_path (avoids polluting the real source tree)
   - Implement test_linter_passes_when_clean by invoking scripts.no_hardcoded_cancel_cost_lint.main() against the actual repo (asserts 0 — Task 2 hardens the regex; this test gates that hardening). Mark this test xfail-strict until Task 2 lands the regex tightening.

Self-verification: cd python ; uv run pytest tests/test_gas_history_ewma.py::test_ewma_correctness tests/test_gas_history_ewma.py::test_ttl_cache -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_gas_history_ewma.py::test_ewma_correctness tests/test_gas_history_ewma.py::test_ttl_cache -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/gas_history.py contains "class GasHistoryCache"
    - File python/src/boros_brain/decision/gas_history.py contains "async def cancel_cost_pendle"
    - File python/src/boros_brain/decision/gas_history.py contains "fee_history"
    - File python/src/boros_brain/decision/gas_history.py contains "chain_time.now_cached"
    - grep -q "self.last_value_pendle" python/src/boros_brain/decision/gas_history.py
    - python3 scripts/no_time_time_lint.py exits 0 (the new file MUST NOT use time.time())
    - cd python ; uv run pytest tests/test_gas_history_ewma.py::test_ewma_correctness -x exits 0
    - cd python ; uv run pytest tests/test_gas_history_ewma.py::test_ttl_cache -x exits 0
  </acceptance_criteria>
  <done>GasHistoryCache implemented; EWMA correctness and TTL cache tests GREEN; chain-time discipline preserved.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Tighten lint scripts — no_hardcoded_cancel_cost, no_threshold_dials (DECIDE-03 / DECIDE-04)</name>
  <files>
    scripts/no_hardcoded_cancel_cost_lint.py,
    scripts/no_threshold_dials_lint.py,
    python/tests/test_no_threshold_dials_lint.py,
    python/tests/test_gas_history_ewma.py
  </files>
  <read_first>
    - scripts/no_hardcoded_cancel_cost_lint.py (skeleton from 04-01 — we tighten the regex and the ALLOWED_FILES allowlist)
    - scripts/no_threshold_dials_lint.py (skeleton from 04-01 — we tighten the regex and ALLOWED_FILES)
    - scripts/no_time_time_lint.py (canonical lint structure — verbatim model)
    - python/src/boros_brain/decision/config.py (after Plan 04-02 — Phase-4 BreakerConfig sub-models with `_threshold` style names; the lint must allow these inside breakers)
    - python/src/boros_brain/decision/gas_history.py (just landed — only legit owner of cancel_cost assignments)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (DECIDE-03 lint pattern lines 446-462; DECIDE-04 audit lines 466-481)
  </read_first>
  <behavior>
    no_hardcoded_cancel_cost_lint.py — finalize:
      - PROTECTED_DIRS = ("python/src/boros_brain/decision/",)
      - ALLOWED_FILES = {"python/src/boros_brain/decision/gas_history.py"}  (the only legit owner)
      - PATTERN regex: `\bcancel_cost(?:_pendle)?\s*=\s*\d+\.?\d*` — matches assignments to literal numerics. The legitimate gas_history.py code uses `self.last_value_pendle = float(pendle)` and `cancel_cost = await gas_cache.cancel_cost_pendle(...)` (await, not literal) so the regex does NOT match the legitimate paths.
      - Exit 0 on a clean tree; exit 1 on any match.

    no_threshold_dials_lint.py — finalize:
      - PROTECTED_DIRS = ("python/src/boros_brain/decision/",)
      - ALLOWED_FILES allowlist:
          * python/src/boros_brain/decision/config.py  (BreakerConfig sub-models legitimately use *_threshold names)
          * python/src/boros_brain/decision/breakers/__init__.py
      - PATTERN: matches identifier names ending in `_threshold`, `_dial`, or `_cutoff` followed by `:` (Pydantic field) or `=` (assignment). Regex: `\b\w+_(?:threshold|dial|cutoff)\s*[:=]`.
      - Decision modules outside the ALLOWED_FILES list MUST NOT introduce such names.
      - Exit 0 on a clean tree; exit 1 on any match.

    Tests turn GREEN:
    - test_no_threshold_dials_lint.py::test_audit_passes_on_main: invoke main(); assert exit code 0.
    - test_no_threshold_dials_lint.py::test_audit_catches_threshold_field: write tmp file outside ALLOWED_FILES with `cancel_threshold: float = 0.5`; assert exit 1.
    - test_gas_history_ewma.py::test_linter_passes_when_clean: invoke; assert exit 0 (was xfail-strict; flip to non-xfail).
    - test_gas_history_ewma.py::test_linter_catches_hardcoded: must continue to PASS after the regex is finalized.
  </behavior>
  <action>
1. Read scripts/no_hardcoded_cancel_cost_lint.py (skeleton from Plan 04-01). Update:
   - PROTECTED_DIRS already correct.
   - ALLOWED_FILES = {"python/src/boros_brain/decision/gas_history.py"}.
   - PATTERN = re.compile(r"\bcancel_cost(?:_pendle)?\s*=\s*\d+\.?\d*").
   - The main() / _scan() / _all_protected_files() body verbatim from no_time_time_lint.py — already done in 04-01 skeleton.
   - Confirm running against the current decision/ tree exits 0 (gas_history.py uses `self.last_value_pendle = float(pendle)` which does NOT match `cancel_cost*` regex; if it accidentally matches, the allowlist excludes the file).

2. Read scripts/no_threshold_dials_lint.py (skeleton from Plan 04-01). Update:
   - PROTECTED_DIRS already correct.
   - ALLOWED_FILES = {"python/src/boros_brain/decision/config.py", "python/src/boros_brain/decision/breakers/__init__.py"}.
   - PATTERN = re.compile(r"\b\w+_(?:threshold|dial|cutoff)\s*[:=]").
   - Confirm running against the current decision/ tree exits 0 (engine.py + gas_history.py do not contain such names; config.py is in ALLOWED_FILES).

3. Update python/tests/test_no_threshold_dials_lint.py:
   - Remove any importorskip / xfail wrappers; tests are now expected to PASS.
   - test_audit_passes_on_main: imports scripts.no_threshold_dials_lint and calls main(); asserts return code 0.
   - test_audit_catches_threshold_field: writes a tmp file `python/src/boros_brain/decision/_lint_fixture_dial_test.py` with content `dummy_threshold: float = 0.5\n`; calls main(); asserts return 1; deletes the tmp file (use try/finally).

4. Update python/tests/test_gas_history_ewma.py::test_linter_passes_when_clean and test_linter_catches_hardcoded:
   - Remove xfail markers.
   - test_linter_passes_when_clean: imports scripts.no_hardcoded_cancel_cost_lint and calls main(); asserts return 0.
   - test_linter_catches_hardcoded: writes `python/src/boros_brain/decision/_lint_fixture_cost_test.py` with `cancel_cost = 0.5`; calls main(); asserts return 1; deletes the file.

Self-verification: both lint scripts exit 0 on the current repo; both test files PASS.
  </action>
  <verify>
    <automated>python3 scripts/no_hardcoded_cancel_cost_lint.py ; python3 scripts/no_threshold_dials_lint.py ; cd python ; uv run pytest tests/test_no_threshold_dials_lint.py tests/test_gas_history_ewma.py -x</automated>
  </verify>
  <acceptance_criteria>
    - grep -q 'ALLOWED_FILES = {"python/src/boros_brain/decision/gas_history.py"}' scripts/no_hardcoded_cancel_cost_lint.py
    - grep -q 'cancel_cost(?:_pendle)?' scripts/no_hardcoded_cancel_cost_lint.py
    - grep -q "config.py" scripts/no_threshold_dials_lint.py
    - grep -q "_threshold|_dial|_cutoff" scripts/no_threshold_dials_lint.py
    - python3 scripts/no_hardcoded_cancel_cost_lint.py exits 0
    - python3 scripts/no_threshold_dials_lint.py exits 0
    - cd python ; uv run pytest tests/test_no_threshold_dials_lint.py -x exits 0
    - cd python ; uv run pytest tests/test_gas_history_ewma.py -x exits 0
  </acceptance_criteria>
  <done>Both lint scripts hardened and pass on Phase-4-final main; their test files turn GREEN.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: DecisionEngine.evaluate() — async EV cancel rule (DECIDE-01 / DECIDE-02)</name>
  <files>
    python/src/boros_brain/decision/engine.py,
    python/tests/test_decision_engine_ev_equation.py,
    python/tests/test_decision_engine_voluntary_branch.py
  </files>
  <read_first>
    - python/src/boros_brain/loss_model/expected_loss.py (canonical sync model with typed-error propagation — verbatim shape model)
    - python/src/boros_brain/fill_model/predict.py (line 53 — predict signature with current_chain_ts; line 91 fit_age_s)
    - python/src/boros_brain/fill_model/schemas.py (PredictInput, PredictOutput, FillModelStaleFeatureError, FillModelNoFreshFitError)
    - python/src/boros_brain/loss_model/schemas.py (ExpectedLossInput, ExpectedLossOutput, LossModelNoFreshGridError)
    - python/src/boros_brain/reward_model/r_capped.py (r_capped_curve signature)
    - python/src/boros_brain/reward_model/schemas.py (RewardCurveInput, RewardCurveOutput, regime Literal)
    - python/src/boros_brain/decision/schemas.py (after 04-02 — EvaluateInput, EvaluateOutput, all 16 input fields and 12 output fields)
    - python/src/boros_brain/decision/gas_history.py (just landed in Task 1)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (DECIDE-01 §, lines 281-385; Code Examples lines 1330-1438; DECIDE-02 §, lines 388-411)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (engine.py pattern lines 100-150)
    - python/tests/test_decision_engine_ev_equation.py (RED tests — must turn GREEN)
    - python/tests/test_decision_engine_voluntary_branch.py (RED tests — must turn GREEN)
  </read_first>
  <behavior>
    engine.py exposes:
      async def evaluate(req: EvaluateInput, *, sqlite_path: Path, config: BotConfig,
                        gas_cache: GasHistoryCache, w3) -> EvaluateOutput

    Implementation per RESEARCH §Code Examples (lines 1356-1438) verbatim:

    1. Pull P(fill) via predict(PredictInput(...), sqlite_path=sqlite_path, config=config). predict is sync — call directly (NO await). Errors propagate (FillModelStaleFeatureError, FillModelNoFreshFitError) — no try/except.
    2. Pull E[loss|fill] via expected_loss(ExpectedLossInput(...), sqlite_path=sqlite_path, config=config). Sync. LossModelNoFreshGridError propagates.
    3. Compute R_share via r_capped_curve(RewardCurveInput(...)). Pure function (no I/O).
    4. Compute cancel_cost via await gas_cache.cancel_cost_pendle(w3=w3, config=config). Async.
    5. p_no_fill_unpurged = (1 - p_fill) * (1 - p_purge); p_purge from req.p_purge (default 0.0; SAFE-04 informs).
    6. Branch on config.strategy.voluntary_cancel_forfeits_accumulated:
       - True (PUNITIVE): ev_hold = r_share * p_no_fill_unpurged - e_loss * p_fill - cancel_cost * p_purge - sunk
                          where sunk = req.r_me_per_epoch_pendle_accumulated_so_far
                          branch = "punitive"
       - False (BENIGN — default): ev_hold = r_share * p_no_fill_unpurged - e_loss * p_fill - cancel_cost * p_purge
                                    branch = "benign"
    7. decision_kind = "CANCEL" if ev_hold < 0 else "HOLD" (PLACE branch only triggered when caller passes a synthetic-place-candidate order; v0.5 main loop handles this externally — engine returns HOLD/CANCEL only for in-flight orders).
    8. Return EvaluateOutput with all 12 fields populated. reasoning dict carries order_id, market_id, side, and the per-step intermediate values (p_no_fill_unpurged, etc.) for operator audit.

    Error policy: per Pitfall #7, the engine NEVER swallows model errors. The coordinator (Plan 04-06) is the single try/except point at the loop boundary. Tests assert pytest.raises propagation.

    Tests turn GREEN:
    - test_ev_sign_matches_decision: HOLD case
    - test_ev_sign_negative_yields_cancel: CANCEL case
    - test_ev_monotonicity: hypothesis property over (p_fill, r_share)
    - test_propagates_predict_errors: monkeypatch predict; assert raises
    - test_propagates_loss_errors: monkeypatch expected_loss; assert raises
    - test_branches_diverge_on_calibrated_scenario: parametrize forfeits ∈ {False, True}
    - test_default_branch_is_benign: default config; assert branch == "benign"
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/engine.py with the exact body from RESEARCH §Code Examples (lines 1330-1438). Imports:
   ```
   from __future__ import annotations
   from pathlib import Path
   import structlog
   from ..config.schema import BotConfig
   from ..fill_model.predict import predict
   from ..fill_model.schemas import (FillModelNoFreshFitError, FillModelStaleFeatureError, PredictInput)
   from ..loss_model.expected_loss import expected_loss
   from ..loss_model.schemas import ExpectedLossInput, LossModelNoFreshGridError
   from ..reward_model.r_capped import r_capped_curve
   from ..reward_model.schemas import RewardCurveInput
   from .gas_history import GasHistoryCache
   from .schemas import EvaluateInput, EvaluateOutput
   log = structlog.get_logger(__name__)
   __all__ = ["evaluate"]
   ```

   Function body — use the verbatim code from RESEARCH §Code Examples §Engine evaluator. Key invariants:
   - SYNC predict() and expected_loss() calls (NO await).
   - r_capped_curve is sync (closed-form).
   - gas_cache.cancel_cost_pendle is async — await it.
   - No try/except around model calls — errors propagate to caller.
   - Branch on config.strategy.voluntary_cancel_forfeits_accumulated.
   - reasoning dict includes: order_id, market_id, side, p_no_fill_and_unpurged, p_purge, sunk_if_punitive, voluntary_cancel_branch.

2. Update python/tests/test_decision_engine_ev_equation.py — remove importorskip; implement the 5 test functions per <behavior>. Use the seed_loss_grid_artifact, seed_competition_history, seed_market_reward_calibration fixtures from conftest. For test_propagates_predict_errors, use monkeypatch.setattr("boros_brain.fill_model.predict.predict", _raises_stale). Same for loss model.

3. Update python/tests/test_decision_engine_voluntary_branch.py — implement test_branches_diverge_on_calibrated_scenario and test_default_branch_is_benign. The calibrated scenario for divergence: build EvaluateInput with r_me_per_epoch_pendle_accumulated_so_far=8.0; r_share=2.0, p_fill=0.05, e_loss=20.0, cancel_cost≈0 (mock w3.eth.fee_history to return tiny base fees). Benign EV ≈ 2*0.95 - 20*0.05 - 0 ≈ 0.9 (HOLD). Punitive EV ≈ 0.9 - 8 ≈ -7.1 (CANCEL). Assert distinguishable decisions.

Self-verification: cd python ; uv run pytest tests/test_decision_engine_ev_equation.py tests/test_decision_engine_voluntary_branch.py -x exits 0 (all tests pass).
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_decision_engine_ev_equation.py tests/test_decision_engine_voluntary_branch.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/engine.py contains "async def evaluate"
    - File python/src/boros_brain/decision/engine.py contains "from ..fill_model.predict import predict"
    - File python/src/boros_brain/decision/engine.py contains "from ..loss_model.expected_loss import expected_loss"
    - File python/src/boros_brain/decision/engine.py contains "from ..reward_model.r_capped import r_capped_curve"
    - File python/src/boros_brain/decision/engine.py contains "voluntary_cancel_forfeits_accumulated"
    - File python/src/boros_brain/decision/engine.py contains 'decision = "CANCEL" if'
    - File python/src/boros_brain/decision/engine.py does NOT contain "try:" wrapping the predict/expected_loss/r_capped_curve calls (Pitfall #7 — errors propagate)
    - python3 scripts/no_hardcoded_cancel_cost_lint.py exits 0 (engine.py uses await gas_cache, no literal cancel_cost = N)
    - python3 scripts/no_threshold_dials_lint.py exits 0 (engine.py contains no _threshold names)
    - python3 scripts/no_time_time_lint.py exits 0 (engine.py uses no time.time())
    - cd python ; uv run pytest tests/test_decision_engine_ev_equation.py -x exits 0
    - cd python ; uv run pytest tests/test_decision_engine_voluntary_branch.py -x exits 0
  </acceptance_criteria>
  <done>engine.evaluate() implemented; DECIDE-01 / DECIDE-02 tests GREEN; engine source clean against all three lint scripts.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Architecture nodes for engine + gas_history + edges</name>
  <files>
    docs/architecture.yml,
    docs/ARCHITECTURE.md
  </files>
  <read_first>
    - docs/architecture.yml (current — find Phase 4 Wave 1 foundation block from 04-02)
    - docs/ARCHITECTURE.md (current Phase 4 Wave 1 Mermaid block from 04-02)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (Architecture Manifest Delta §, lines 957-1090)
    - scripts/architecture_lint.py
  </read_first>
  <behavior>
    Append in same commit as engine.py + gas_history.py:
    Module nodes:
      - brain.decision.engine (path engine.py; public_functions [evaluate])
      - brain.decision.gas_history (path gas_history.py; public_functions [GasHistoryCache, cancel_cost_pendle])
    External node:
      - external.arbitrum.fee_history (path: AsyncWeb3.eth.fee_history endpoint)
    Edges:
      - brain.decision.engine -> brain.fill_model.predict (calls)
      - brain.decision.engine -> brain.loss_model.expected_loss (calls)
      - brain.decision.engine -> brain.reward_model.r_capped (calls)
      - brain.decision.engine -> brain.decision.gas_history (calls)
      - brain.decision.engine -> brain.decision.schemas (depends-on shapes — implicit; not always recorded but include for completeness)
      - brain.decision.gas_history -> external.arbitrum.fee_history (calls)
      - brain.decision.gas_history -> brain.data.chain_time (calls)
      - brain.decision.engine -> config.strategy.voluntary_cancel_forfeits_accumulated (depends-on-config)
      - brain.decision.gas_history -> config.decision.cancel_cost_ewma_alpha (depends-on-config)
      - brain.decision.gas_history -> config.decision.cancel_cost_ttl_s (depends-on-config)
      - brain.decision.gas_history -> config.decision.cancel_cost_block_window (depends-on-config)
      - brain.decision.gas_history -> config.execution.cancel_gas_units_estimate (depends-on-config)
      - brain.decision.gas_history -> config.pricing.eth_price_usd (depends-on-config)
      - brain.decision.gas_history -> config.pricing.pendle_price_usd (depends-on-config)
    Mermaid: extend Phase 4 sub-graph with engine + gas_history + external.arbitrum.fee_history.
  </behavior>
  <action>
1. Read docs/architecture.yml to find the Phase 4 Wave 1 foundation block (around the area lines 1090-1100 per 04-02 commit).

2. Append after the Wave 1 foundation block, before edges section starts:
   ```yaml
   # ── Phase 4 Wave 2A engine+gas_history — Plan 04-03 ────────────
   - id: brain.decision.engine
     type: module
     process: brain
     path: python/src/boros_brain/decision/engine.py
     public_functions: [evaluate]

   - id: brain.decision.gas_history
     type: module
     process: brain
     path: python/src/boros_brain/decision/gas_history.py
     public_functions: [GasHistoryCache]

   - id: external.arbitrum.fee_history
     type: external_api
     process: external
     path: AsyncWeb3.eth.fee_history (JSON-RPC eth_feeHistory)
     public_functions: []
   ```

3. Append edges to the Phase 4 edges section (after the Wave 1 edges from 04-02):
   ```yaml
   # ── Phase 4 Wave 2A engine+gas_history edges — Plan 04-03 ──────
   - {from: brain.decision.engine, to: brain.fill_model.predict, type: calls}
   - {from: brain.decision.engine, to: brain.loss_model.expected_loss, type: calls}
   - {from: brain.decision.engine, to: brain.reward_model.r_capped, type: calls}
   - {from: brain.decision.engine, to: brain.decision.gas_history, type: calls}
   - {from: brain.decision.gas_history, to: external.arbitrum.fee_history, type: calls}
   - {from: brain.decision.gas_history, to: brain.data.chain_time, type: calls}
   - {from: brain.decision.engine, to: config.strategy.voluntary_cancel_forfeits_accumulated, type: depends-on-config}
   - {from: brain.decision.gas_history, to: config.decision.cancel_cost_ewma_alpha, type: depends-on-config}
   - {from: brain.decision.gas_history, to: config.decision.cancel_cost_ttl_s, type: depends-on-config}
   - {from: brain.decision.gas_history, to: config.decision.cancel_cost_block_window, type: depends-on-config}
   - {from: brain.decision.gas_history, to: config.execution.cancel_gas_units_estimate, type: depends-on-config}
   - {from: brain.decision.gas_history, to: config.pricing.eth_price_usd, type: depends-on-config}
   - {from: brain.decision.gas_history, to: config.pricing.pendle_price_usd, type: depends-on-config}
   ```

4. Update docs/ARCHITECTURE.md — extend the Phase 4 Wave 1 Mermaid sub-graph or append a Phase 4 Wave 2A sub-graph with engine + gas_history + external.arbitrum.fee_history nodes and the calls edges.

5. Run python3 scripts/architecture_lint.py — must exit 0.

Self-verification: grep returns the expected new node IDs and edges.
  </action>
  <verify>
    <automated>python3 scripts/architecture_lint.py</automated>
  </verify>
  <acceptance_criteria>
    - grep -q "brain.decision.engine" docs/architecture.yml
    - grep -q "brain.decision.gas_history" docs/architecture.yml
    - grep -q "external.arbitrum.fee_history" docs/architecture.yml
    - grep -q "brain.decision.engine, to: brain.fill_model.predict" docs/architecture.yml
    - grep -q "brain.decision.engine, to: brain.loss_model.expected_loss" docs/architecture.yml
    - grep -q "brain.decision.engine, to: brain.reward_model.r_capped" docs/architecture.yml
    - grep -q "brain.decision.gas_history, to: external.arbitrum.fee_history" docs/architecture.yml
    - grep -q "Phase 4 Wave 2A\|Phase 4 Wave 2" docs/ARCHITECTURE.md
    - python3 scripts/architecture_lint.py exits 0
  </acceptance_criteria>
  <done>Engine + gas_history nodes, external fee_history node, and 13 edges atomically registered; architecture_lint passes.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Wiki write-back — ev-cancel-rule-implementation, gas-history-ewma</name>
  <files>
    python/tests/test_decision_engine_ev_equation.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (LLM Wiki Pages to Write-Back, lines 1532-1557)
  </read_first>
  <behavior>
    File two wiki pages:
    - ev-cancel-rule-implementation-v05.md — the equation as implemented in engine.py with line refs and the benign/punitive branch rationale.
    - gas-history-ewma-cancel-cost.md — DECIDE-03 wei->PENDLE conversion path, EWMA alpha=0.1 / 100-block window justification, daily-rescreen freshness discipline (Pitfall #5), and the linter that mechanizes the invariant.

    Touch test_decision_engine_ev_equation.py docstring to add the wiki cross-references.
  </behavior>
  <action>
1. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/ev-cancel-rule-implementation-v05.md with content including:
   - Status: Current
   - The full EV equation: EV_hold = R_share * P(no_fill_and_unpurged) - E[loss|fill] * P(fill) - cancel_cost * P(purge) [- sunk if punitive]
   - Line references into python/src/boros_brain/decision/engine.py for each equation step
   - Benign vs punitive branch rationale (P0-01 resolution; default = benign)
   - Cross-reference to [[voluntary-cancel-reward-behavior]], [[circuit-breakers-v05]]

2. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md with content:
   - Status: Current
   - The wei->PENDLE conversion path with each conversion factor explicitly named
   - EWMA alpha = 0.1 (half-life ~7 blocks ~1.75s); 100-block window (~25s of Arbitrum chain history)
   - TTL = 60s (1 RPC per minute)
   - Pitfall #5 calibration discipline (daily rescreen verifies eth_price_usd / pendle_price_usd freshness)
   - The lint mechanism (no_hardcoded_cancel_cost_lint.py with PROTECTED_DIRS=decision/ and ALLOWED_FILES=gas_history.py)
   - Cross-reference to [[ev-cancel-rule-implementation-v05]], [[run-manifest-writer]]

3. Append to test_decision_engine_ev_equation.py module docstring: a "See [[ev-cancel-rule-implementation-v05]] and [[gas-history-ewma-cancel-cost]] for spec." line.

Self-verification: both files exist with Status: Current.
  </action>
  <verify>
    <automated>test -f "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/ev-cancel-rule-implementation-v05.md"</automated>
  </verify>
  <acceptance_criteria>
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/ev-cancel-rule-implementation-v05.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md" exists
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/ev-cancel-rule-implementation-v05.md"
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md"
    - grep -q "EV_hold" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/ev-cancel-rule-implementation-v05.md"
    - grep -q "alpha" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/gas-history-ewma-cancel-cost.md"
    - grep -q "ev-cancel-rule-implementation-v05\|gas-history-ewma-cancel-cost" python/tests/test_decision_engine_ev_equation.py
  </acceptance_criteria>
  <done>Two wiki pages filed; cross-references in place.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| AsyncWeb3 fee_history -> brain | External RPC; gas history can be temporarily stale or zero on a private-RPC outage. |
| BotConfig pricing knobs -> wei->PENDLE conversion | Operator-calibrated values; staleness reduces accuracy of cancel_cost in PENDLE units. |
| engine.evaluate caller -> error propagation | Engine intentionally does NOT swallow model errors; coordinator (Plan 04-06) catches and routes. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-03-01 | I (Information disclosure) | engine.evaluate reasoning dict | accept | reasoning carries order_id, market_id, side, intermediate values for operator audit. No secrets. The decisions table writer (Plan 04-06) persists this for forensic replay. |
| T-04-03-02 | T (Tampering) | hardcoded cancel_cost regression | mitigate | scripts/no_hardcoded_cancel_cost_lint.py is the mechanical guard; ALLOWED_FILES allowlist locks the only legit owner (gas_history.py). Pre-commit hook runs the lint. |
| T-04-03-03 | T (Tampering) | threshold-dial regression | mitigate | scripts/no_threshold_dials_lint.py with ALLOWED_FILES = {decision/config.py, breakers/__init__.py}. Any future contributor introducing a `cancel_threshold` outside the breaker config families fails the lint. |
| T-04-03-04 | D (Denial of service) | gas_history fee_history RPC stall | mitigate | asyncio.wait_for(timeout=5.0) on the RPC call; on timeout or any exception the cache returns last_value_pendle (stale-but-known) and logs warning. The 1 Hz brain loop is not blocked. |
| T-04-03-05 | I (Information disclosure) | engine error swallowing | mitigate | Pitfall #7 — engine NEVER catches FillModelStaleFeatureError / FillModelNoFreshFitError / LossModelNoFreshGridError. Tests use pytest.raises to enforce. The coordinator's loop boundary is the single try/except in main.py (Plan 04-06). |
| T-04-03-06 | S (Spoofing) | EvaluateOutput voluntary_cancel_branch field | mitigate | The branch is set by the engine itself (not the caller), based on config.strategy.voluntary_cancel_forfeits_accumulated. A Phase 5 backtest sweep ([[voluntary-cancel-reward-behavior]] sanity row) verifies both branches behave as expected. |
</threat_model>

<verification>
After all tasks complete, run:

```
cd python ; uv run pytest tests/test_decision_engine_ev_equation.py tests/test_decision_engine_voluntary_branch.py tests/test_gas_history_ewma.py tests/test_no_threshold_dials_lint.py -x

python3 scripts/no_hardcoded_cancel_cost_lint.py
python3 scripts/no_threshold_dials_lint.py
python3 scripts/no_time_time_lint.py
python3 scripts/architecture_lint.py
python3 scripts/sqlite_writer_lint.py --root .
```

All MUST exit 0. The Phase 4 RED tests for DECIDE-01..04 are now GREEN.
</verification>

<success_criteria>
- [ ] engine.py + gas_history.py exist; tests for DECIDE-01..04 PASS.
- [ ] Both lint scripts (no_hardcoded_cancel_cost, no_threshold_dials) exit 0 on Phase-4-final main.
- [ ] No drift: sqlite_writer_lint, no_time_time_lint, architecture_lint all exit 0.
- [ ] Architecture.yml + Mermaid Wave-2A delta atomic with source.
- [ ] Two wiki pages filed with Status: Current.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-03-SUMMARY.md` documenting:
- engine.evaluate() implementation (DECIDE-01 / DECIDE-02)
- GasHistoryCache (DECIDE-03)
- 2 lint scripts hardened (DECIDE-03 / DECIDE-04)
- 4 RED tests turned GREEN
- Architecture delta (2 modules + 1 external + 13 edges)
- 2 wiki pages filed
</output>
