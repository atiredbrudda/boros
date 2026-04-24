---
phase: 03-loss-reward-share-models-sizing
plan: 02
subsystem: reward_model
tags: [reward_model, pricing, competition_tracker, market_reward_calibration, botconfig_schema, alembic, locked_d01]
requires:
  - phase: 01
    plan: 02
    provides: [state.fill_model_fits writer pattern, sqlite_writer_lint discipline]
  - phase: 01
    plan: 11
    provides: [DATA-09 economics gate + EPOCHS_PER_YEAR + PENDLE-unit pattern]
  - phase: 02
    plan: 02
    provides: [fill_model.amm_consumption.compute_amm_share_timeseries — sibling AMM-exclusion semantics]
  - phase: 03
    plan: 01
    provides: [LossModelConfig (attached here), FeesConfig nested]
provides:
  modules:
    - brain.reward_model.config (RewardShareModelConfig)
    - brain.reward_model.schemas (RewardCurveInput/Output, CompetitionSnapshot, RegimeLabel, MarketRewardCalibrationSplitError)
    - brain.reward_model.r_capped (r_capped_curve closed-form)
    - brain.reward_model.q_cap (compute_q_cap algebra)
    - brain.reward_model.competition_tracker (CompetitionTracker + run_competition_tracker_loop)
    - brain.reward_model.calibrate (insert_operator_calibration)
    - brain.reward_model.cli (curve | competition-snapshot | calibrate)
    - brain.pricing.config (PricingConfig)
    - brain.state.writers.competition_history (insert_competition_row + get_latest_competition)
    - brain.state.writers.market_reward_calibration (insert_market_reward_calibration + get_latest_market_reward_calibration)
  schema:
    - state.competition_history (Alembic 0005)
    - state.market_reward_calibration (Alembic 0006 — LOCKED D-01)
    - BotConfig.loss_model attached (from 03-01)
    - BotConfig.reward_share_model + BotConfig.pricing added
    - MarketCalibration.reward_calibration: MarketRewardCalibration | None added
  contracts:
    - RewardCurveInput / RewardCurveOutput (Phase-4 LOCKED — Sizer + DecisionEngine consume)
    - CompetitionSnapshot (REWARD-02 storage shape)
    - MarketRewardCalibration Pydantic sub-model with P3-4 split-sum field_validator
affects:
  - python/tests/test_sqlite_migrations.py (table-set assertion updated for tables 11+12)
tech_stack:
  patterns:
    - reward_model + pricing scaffold mirrors fill_model + loss_model package pattern
    - parquet-FIRST DuckDB read for Σ_others (T-03-06 AMM exclusion via order_book_raw)
    - REST + parquet composition with degraded-fallback mirroring e_liq_poller pattern
    - operator-manual calibration → SQLite (data_source='operator' CHECK) per LOCKED D-01
    - three-layer guard: Pydantic field_validator + writer-layer + SQL CHECK
key_files:
  created:
    - python/src/boros_brain/reward_model/__init__.py
    - python/src/boros_brain/reward_model/__main__.py
    - python/src/boros_brain/reward_model/config.py
    - python/src/boros_brain/reward_model/schemas.py
    - python/src/boros_brain/reward_model/r_capped.py
    - python/src/boros_brain/reward_model/q_cap.py
    - python/src/boros_brain/reward_model/competition_tracker.py
    - python/src/boros_brain/reward_model/calibrate.py
    - python/src/boros_brain/reward_model/cli.py
    - python/src/boros_brain/pricing/__init__.py
    - python/src/boros_brain/pricing/config.py
    - python/src/boros_brain/state/writers/competition_history.py
    - python/src/boros_brain/state/writers/market_reward_calibration.py
    - python/src/boros_brain/state/migrations/versions/0005_competition_history.py
    - python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py
    - python/tests/test_reward_curve.py
    - python/tests/test_competition_tracker.py
    - python/tests/test_market_reward_calibration.py
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/reward-cap-geometry-v05.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/competition-tracker-data-sources-v05.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/market-reward-calibration-operator-workflow.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/e-liq-per-epoch-source-decision.md"
  modified:
    - python/src/boros_brain/config/schema.py (extend BotConfig + add MarketRewardCalibration; attach loss_model from 03-01)
    - python/src/boros_brain/state/schemas.sql (append competition_history + market_reward_calibration DDL)
    - python/tests/test_sqlite_migrations.py (table-set updated for tables 11+12)
    - strategy/v0.5-default.yaml (Phase-3 knob block)
decisions:
  - "BotConfig.loss_model attached here per Plan 03-01's deferred TODO; same commit lands LossModelConfig nested instance with default_factory"
  - "data_source='operator' is hardcoded into SQL VALUES literal in market_reward_calibration writer — NOT a caller kwarg. Matches LOCKED D-01 single-lineage discipline."
  - "Σ_others reads parquet.order_book_raw (NOT combined) per T-03-06 — AMM-share is the (combined - raw) delta and AMMs do not compete for LO Liquidity Rewards"
  - "competition_tracker.rest_degraded event emits exactly once per degraded window; resets on first successful REST recovery (mirrors HeartbeatMonitor fire-once LostSibling pattern)"
  - "v0.5 _sum_q_me uses YU↔PENDLE 1:1 placeholder (1e18 wei divisor for string sizes); Plan 03-03 Sizer wires the proper notional_per_yu_usd / pendle_price_usd conversion"
  - "cap_budget formula evaluates left-to-right to 2.74 PENDLE at \$100 / 137 PENDLE at \$5k (1000% APR per-account cap converted to PENDLE/epoch). Plan-prose claim of 0.274 / 13.7 was a stale arithmetic; tests use the correct values."
  - "SizerConfig attachment intentionally deferred to Plan 03-03 (avoids forward-import order issues); sizer field is commented out in BotConfig with explicit TODO marker"
metrics:
  duration_min: 30
  tasks_completed: 4
  files_created: 22
  files_modified: 4
  total_tests_added: 24
  tests_pass: 24
  tests_skip: 0
  completed: "2026-04-24"
---

# Phase 3 Plan 02: RewardShareModel + CompetitionTracker + LOCKED D-01 Calibration Summary

REWARD-01 (closed-form capped pro-rata r_capped curve with regime classification),
REWARD-02 (CompetitionTracker REST + parquet composition with AMM-share
exclusion), REWARD-04 (Q_cap algebra), and the LOCKED D-01 operator-manual
calibration path — `MarketRewardCalibration` Pydantic sub-model + new SQLite
table `state.market_reward_calibration` with `data_source='operator'` CHECK +
calibrate CLI subcommand. Lands the Phase-3 BotConfig schema delta (attaches
LossModelConfig from 03-01, adds RewardShareModelConfig + PricingConfig +
MarketRewardCalibration sub-model, extends MarketCalibration).

## Core Deliverables

### 1. `RewardShareModelConfig` + `PricingConfig` (PROTO-04 SSoT)

`brain.reward_model.config` exports `RewardShareModelConfig` (5 knobs:
`competition_poll_interval_s`, `sigma_others_min_pendle`, `epoch_days`,
`cap_apr_multiple`, `fallback_to_parquet_after_rest_fails_n`). `brain.pricing.config`
exports `PricingConfig` (4 knobs: `pendle_price_usd`, `price_source` Literal
manual|chainlink|pyth, `price_staleness_warn_s`, `price_staleness_halt_s`).

Both are local StrictBase (extra='forbid', frozen=True) — same circular-import
discipline as `fill_model.config`/`loss_model.config`. Reflection-walked into
RUN_MANIFEST automatically; `test_manifest_contains_all_knobs` confirms.

### 2. `BotConfig` schema delta (single SSoT)

`config/schema.py` extended:
- `from ..loss_model.config import LossModelConfig` + `from ..pricing.config import PricingConfig` + `from ..reward_model.config import RewardShareModelConfig`.
- New `class MarketRewardCalibration(StrictBase)` with 5 fields (`e_liq_per_epoch_pendle`, `long_side_split`, `short_side_split`, `calibrated_at_utc`, `source: Literal["dapp_ui","team_statement","pendle_docs"]`) and `_splits_sum_to_one` field_validator (P3-4 guard).
- `MarketCalibration.reward_calibration: MarketRewardCalibration | None = None` (optional, backward-compatible).
- `BotConfig` adds `loss_model`, `reward_share_model`, `pricing` sub-models with `default_factory=...`. SizerConfig is deferred to Plan 03-03 with a clearly-marked commented-out TODO line.

`test_manifest_contains_all_knobs` reflection auto-surfaces all new leaves; no
manual test edit was required.

### 3. `r_capped_curve` (REWARD-01) + `compute_q_cap` (REWARD-04)

`brain.reward_model.r_capped.r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput`
implements the closed-form:
```
R_uncapped = E_liq × side_split × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)
cap_budget = 10 × collateral_usd × (epoch_days / 365) / pendle_price_usd
R_capped   = min(R_uncapped, cap_budget)
```
With three-way regime classification (`sub_cap`/`cap_binding`/`market_saturated`)
absorbing PITFALLS §A4 kinked-curve geometry. T-03-03 mitigation: explicit
`denom == 0.0 or q_me == 0.0` guard at formula entry mirrors
`screener/economics_gate.py` divide-by-zero pattern. Fees are NOT subtracted
here — they're absorbed inside `LossModel.expected_loss`
(see [[fee-cost-term-in-expected-loss]]).

`brain.reward_model.q_cap.compute_q_cap(...)` returns the `Q_me` at which
`R_uncapped` first equals `cap_budget`:
```
Q_cap = Σ_others × cap_budget / (E_liq × side_split × t_frac - cap_budget × t_frac)
```
Returns `math.inf` when the denominator <= 0 (cap unreachable at any finite Q_me).

### 4. `CompetitionTracker` (REWARD-02)

`brain.reward_model.competition_tracker.CompetitionTracker.run_one_cycle()`
composes:
- **Q_me** via `POST /open-api/v2/accounts/all-limit-orders` (REST, exponential backoff).
- **Σ_others** via DuckDB SQL aggregation over `parquet.order_book_raw` within `[clo_lower, clo_upper]` at the latest snapshot ≤ chain_ts.

`Σ_others = max(0, total_raw_book - Q_me)`. **Reads `order_book_raw` not
`order_book_combined`** — T-03-06 mitigation; AMMs do not compete for LO
Liquidity Rewards. Phase-2 fill_model.amm_consumption sibling logic informs
the rationale.

Degraded fallback: after 5 consecutive REST failures
(`fallback_to_parquet_after_rest_fails_n`), tracker writes `data_source='fallback_parquet_only'`,
estimates Q_me from `state.open_orders` SQLite, and emits
`competition_tracker.rest_degraded` event exactly once until recovery (fire-once
discipline mirrors `HeartbeatMonitor.LostSibling`).

`async run_competition_tracker_loop(config, run_id, *, conn, rest, event_pub)`
is the long-lived asyncio task — Plan 03-04 will spawn it from `main.py`.

### 5. Calibrate CLI (LOCKED D-01)

`brain.reward_model.calibrate.insert_operator_calibration` is the
operator-manual calibration entry point. Three-layer guard:
1. Pydantic `MarketRewardCalibration` constructor fires `_splits_sum_to_one`
   field_validator (P3-4 guard) BEFORE any DB layer.
2. Writer-layer (`state.writers.market_reward_calibration`) belt-and-braces.
3. SQL `CHECK(data_source = 'operator')`, `BETWEEN 0.0 AND 1.0`,
   non-negative-e_liq, source-enum CHECK constraints.

CLI surface:
```
python -m boros_brain.reward_model {curve|competition-snapshot|calibrate}
```
MANIFEST-FIRST boot (PROTO-01). Exit codes: 0 success, 1 domain error,
2 ConfigError / Pydantic ValidationError. Tier `'reward_model'` joins the
existing structlog tier set.

### 6. Single writers + Alembic 0005/0006

- `brain.state.writers.competition_history.insert_competition_row` is the only
  write path for `competition_history` (`scripts/sqlite_writer_lint.py` will
  catch any drift on commit). Writer rejects `data_source` outside
  `{live, fallback_parquet_only}` before SQL round-trip.
- `brain.state.writers.market_reward_calibration.insert_market_reward_calibration`
  is the only write path for `market_reward_calibration`. Hardcodes
  `data_source='operator'` in the SQL VALUES literal — NOT a caller kwarg.
  Validates source enum + split-sum + non-negative-e_liq before SQL.

Alembic migrations 0005 (competition_history) and 0006 (market_reward_calibration)
are idempotent (`_has_table` / `_has_index` gates) and apply cleanly on a fresh
DB. `test_sqlite_migrations.test_all_8_tables_exist_after_migration` updated
for tables 11 + 12.

## Interfaces Published for Plan 03-03 / 03-04 / Phase 4 Consumption

```python
# REWARD-01/02 LOCKED contracts — Plan 03-03 Sizer + Phase 4 DecisionEngine consume

class RewardCurveInput(StrictBase):
    market_id: str
    side: Literal["long", "short"]
    q_me_pendle: float
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float
    t_frac: float
    collateral_usd: float
    pendle_price_usd: float
    epoch_days: float

class RewardCurveOutput(StrictBase):
    r_uncapped_pendle: float
    r_capped_pendle: float
    cap_budget_pendle: float
    regime: Literal["sub_cap", "cap_binding", "market_saturated"]

def r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput: ...

def compute_q_cap(*, sigma_others_pendle, e_liq_per_epoch_pendle, side_split,
                  t_frac, collateral_usd, pendle_price_usd, epoch_days) -> float: ...

class CompetitionSnapshot(StrictBase):
    market_id: str
    polled_at_utc: str
    chain_ts: int
    q_me_pendle: float
    sigma_others_pendle: float
    data_source: Literal["live", "fallback_parquet_only"]
    run_id: str

# Phase-3 LOCKED D-01 storage shape
class MarketRewardCalibration(StrictBase):
    e_liq_per_epoch_pendle: float  # Field(ge=0.0)
    long_side_split: float          # Field(ge=0.0, le=1.0)
    short_side_split: float         # Field(ge=0.0, le=1.0); P3-4 split-sum validator
    calibrated_at_utc: str
    source: Literal["dapp_ui", "team_statement", "pendle_docs"] = "dapp_ui"
```

## Test Results

- **Plan tests added**: 24 (12 reward curve + 5 competition tracker + 7 calibration).
- **All passed.**
- **Migration test**: 8/8 PASS (table-set updated for tables 11 + 12).
- **Plan-relevant suite**: `test_reward_curve` + `test_competition_tracker` +
  `test_market_reward_calibration` + `test_loss_model_*` (Plan 03-01) +
  `test_manifest_contains_all_knobs` + `test_sqlite_migrations` +
  `test_e_liq_poller` + `test_economics_kill_switch` + `test_config_round_trip`
  → **79 PASS + 1 SKIP** (the 1 skip is a Phase-5 backtest integration
  placeholder from Plan 03-01).

| File | Tests |
|------|-------|
| `test_reward_curve.py` | 12 (sub_cap, cap_binding, market_saturated, q_me=0 guard, T-03-03 div-by-zero, pendle_price=0 raises, negative-e_liq raises, q_cap inf-degenerate, q_cap finite at \$100, q_cap at \$5k, q_cap pendle_price=0 raises, monotone non-decreasing) |
| `test_competition_tracker.py` | 5 (one-row-per-cycle, sigma excludes q_me, source-grep order_book_raw not combined, fallback after 5 fails, degraded event once-only) |
| `test_market_reward_calibration.py` | 7 (round-trip, P3-4 split-mismatch raises, SQL CHECK rejects non-operator, negative-e_liq raises, source enum rejects invalid, CLI smoke success exit 0, CLI smoke split-mismatch exit 2) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] cap_budget formula numerical claim was wrong in plan prose**

- **Found during:** Task 2 verification (`test_q_cap_at_5k_collateral` initially failed with `q_cap=84.0` against the plan's `(1, 10)` bound).
- **Issue:** Plan prose claimed `cap_budget ≈ 0.274` PENDLE at \$100 / `13.7` at \$5k. Left-to-right evaluation of `10 × collateral_usd × (epoch_days / 365) / pendle_price_usd` actually yields `2.74` and `137` respectively. The 1000% APR per-account cap converted to PENDLE/epoch at \$100 is `100 × 10 / 365 / 7 × 7 = 1000/365 = 2.74` — straightforward arithmetic. Plan's 0.274 / 13.7 was a 10× error.
- **Fix:** Used the correct arithmetic in `r_capped_curve` + `compute_q_cap` implementations, updated `test_q_cap_finite_at_100_collateral_ethusdt` and `test_q_cap_at_5k_collateral` bounds and docstrings to match the correct math. The Phase 3 ROADMAP success criterion (sub_cap regime at \$100, cap_binding at scale-up) is still satisfied — only the absolute PENDLE numbers are 10× larger than the plan claimed.
- **Files modified:** `python/tests/test_reward_curve.py` (test bounds + docstrings).
- **Commit:** 9a33f7e.

**2. [Plan-aligned] BotConfig.loss_model attachment is the contract Plan 03-01 deferred to this plan**

- **Found during:** Task 1 BotConfig extension.
- **Issue:** Plan 03-01 SUMMARY explicitly notes "BotConfig.loss_model attachment deferred to Plan 03-02 — `_get_loss_model_config(config)` helper falls back to default `LossModelConfig()`". This plan honors that contract.
- **Fix:** Added `loss_model: LossModelConfig = Field(default_factory=LossModelConfig)` line to `BotConfig` per the plan's `<interfaces>` block. Plan 03-01's helper transparently switches to operator-supplied config now.
- **Files modified:** `python/src/boros_brain/config/schema.py`.
- **Commit:** 2ece997.

### No Rule-4 (architectural) checkpoints encountered.

## Auth Gates

None. The plan is offline batch + sync query + operator-manual CLI; no
network endpoints requiring auth, no operator-only secrets, no 2FA / email-link
flows.

## Known Stubs / Open TODOs

These are explicitly deferred to Plan 03-04 / 03-03 per the plan's `<deferred>`
expectations — they are NOT bugs:

| TODO | File | Plan that closes it |
|------|------|---------------------|
| `SizerConfig` attachment to BotConfig | `config/schema.py` (commented-out line) | Plan 03-03 |
| Architecture.yml + Mermaid nodes for reward_model + pricing packages | `docs/architecture.yml` | Plan 03-04 |
| Spawn `run_competition_tracker_loop` from main.py | `python/src/boros_brain/main.py` | Plan 03-04 |
| Supersedence Status flip on [[live-e-liq-polling-data-11]] + [[historical-reward-budget-reconstruction-infeasible]] | LLM Wiki | Plan 03-04 |
| `replay.py` pendle_price_usd wiring from `config.pricing` | `loss_model/replay.py` | Plan 03-04 |
| `no_time_time_lint.py` extension to include `reward_model/` | `scripts/no_time_time_lint.py` | Plan 03-04 |
| YU↔PENDLE proper conversion (Sizer notional_per_yu_usd) | `competition_tracker._sum_q_me` v0.5 placeholder | Plan 03-03 |

## Threat Flags

None. The plan introduces three new trust-boundary surfaces — operator CLI →
SQLite, REST → Pydantic+SQLite, parquet→DuckDB — but each is already covered
by the `<threat_model>` register (T-03-02 / T-03-04 / T-03-06 / T-03-07) with
mitigations implemented and tested. No NEW threat-relevant surface beyond what
the plan enumerated.

## TDD Gate Compliance

Plan-level type is `execute` (not `tdd`), but each task's `tdd="true"` was
honored: tests were written alongside implementation (test files committed in
the same task commits as their target modules). Per-task commit hashes:

- Task 1 (2ece997): scaffold reward_model + pricing + Alembic 0005/0006 + BotConfig delta + YAML + writers; test_sqlite_migrations table-set updated.
- Task 2 (9a33f7e): r_capped + q_cap closed-form (12 tests).
- Task 3 (e0625b2): CompetitionTracker + calibrate CLI + 12 tests (5 tracker + 7 calibration).
- Task 4 (no in-repo commit): 4 wiki pages live at `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/` per CLAUDE.md Engineering Protocol 1.

## Self-Check: PASSED

**Files created (in-repo):**
- `python/src/boros_brain/reward_model/__init__.py` — FOUND
- `python/src/boros_brain/reward_model/__main__.py` — FOUND
- `python/src/boros_brain/reward_model/config.py` — FOUND
- `python/src/boros_brain/reward_model/schemas.py` — FOUND
- `python/src/boros_brain/reward_model/r_capped.py` — FOUND
- `python/src/boros_brain/reward_model/q_cap.py` — FOUND
- `python/src/boros_brain/reward_model/competition_tracker.py` — FOUND
- `python/src/boros_brain/reward_model/calibrate.py` — FOUND
- `python/src/boros_brain/reward_model/cli.py` — FOUND
- `python/src/boros_brain/pricing/__init__.py` — FOUND
- `python/src/boros_brain/pricing/config.py` — FOUND
- `python/src/boros_brain/state/writers/competition_history.py` — FOUND
- `python/src/boros_brain/state/writers/market_reward_calibration.py` — FOUND
- `python/src/boros_brain/state/migrations/versions/0005_competition_history.py` — FOUND
- `python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py` — FOUND
- `python/tests/test_reward_curve.py` — FOUND
- `python/tests/test_competition_tracker.py` — FOUND
- `python/tests/test_market_reward_calibration.py` — FOUND

**Files modified (in-repo):**
- `python/src/boros_brain/config/schema.py` — FOUND (extended)
- `python/src/boros_brain/state/schemas.sql` — FOUND (extended)
- `python/tests/test_sqlite_migrations.py` — FOUND (table-set updated)
- `strategy/v0.5-default.yaml` — FOUND (Phase-3 knob block)

**Files created (LLM Wiki, external):**
- `LLM Wiki/.../reward-cap-geometry-v05.md` — FOUND
- `LLM Wiki/.../competition-tracker-data-sources-v05.md` — FOUND
- `LLM Wiki/.../market-reward-calibration-operator-workflow.md` — FOUND
- `LLM Wiki/.../e-liq-per-epoch-source-decision.md` — FOUND

**Commits:**
- 2ece997 — FOUND (Task 1: scaffold + Alembic + BotConfig + YAML)
- 9a33f7e — FOUND (Task 2: r_capped + q_cap + 12 tests)
- e0625b2 — FOUND (Task 3: CompetitionTracker + calibrate + 12 tests)
