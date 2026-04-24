-- Canonical SQLite schema for the boros v0.5 state spine (INFRA-03).
--
-- Source of truth: this file. The Alembic migration 0001_initial_8_tables replays
-- these statements in order; any schema change lands here first and gets a new
-- Alembic revision in the same commit.
--
-- Ownership map (enforced by scripts/sqlite_writer_lint.py):
--   hands (TS sqlite_writer.ts):  open_orders, tx_receipts
--   brain (Python state/writers/<table>.py): decisions, queue_positions,
--     run_manifests, epoch_rewards, clo_history, reward_budget_history, fill_model_fits
--
-- FKs are only enforced when `PRAGMA foreign_keys = ON` (applied per-connection
-- by boros_brain.state.db.open_connection).

-- Enforce FK constraints for this connection (db.py also sets it at open_connection).
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- open_orders  (hands-owned)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS open_orders (
    order_id      TEXT PRIMARY KEY,
    market_id     TEXT NOT NULL,
    side          TEXT NOT NULL CHECK(side IN ('long','short')),
    depth_ticks   INTEGER NOT NULL,
    size_wei      TEXT NOT NULL,            -- wei as string (256-bit safe)
    rate          INTEGER NOT NULL,         -- Boros rate tick
    status        TEXT NOT NULL CHECK(status IN ('filling','cancelled','fully_filled','expired','purged')),
    placed_at_ts  INTEGER NOT NULL,
    run_id        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_open_orders_run_id ON open_orders(run_id);
CREATE INDEX IF NOT EXISTS ix_open_orders_market_status ON open_orders(market_id, status);

-- ---------------------------------------------------------------------------
-- decisions  (brain-owned)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decisions (
    decision_id  TEXT PRIMARY KEY,
    ts_ms        INTEGER NOT NULL,
    run_id       TEXT NOT NULL,
    market_id    TEXT NOT NULL,
    decision     TEXT NOT NULL CHECK(decision IN ('place','hold','cancel','emergency_cancel','no_action')),
    ev_hold      REAL,
    p_fill       REAL,
    e_loss       REAL,
    r_share      REAL,
    reason       TEXT
);
CREATE INDEX IF NOT EXISTS ix_decisions_run_id_ts ON decisions(run_id, ts_ms);

-- ---------------------------------------------------------------------------
-- tx_receipts  (hands-owned)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tx_receipts (
    tx_hash           TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL,
    submitted_at_ts   INTEGER NOT NULL,
    confirmed_at_ts   INTEGER,
    status            TEXT NOT NULL CHECK(status IN ('pending','confirmed','reverted','dropped')),
    gas_used          INTEGER,
    intent            TEXT NOT NULL,         -- 'place'|'cancel'|'close'|'claim'|'approve'|...
    related_order_id  TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_receipts_run_id ON tx_receipts(run_id);

-- ---------------------------------------------------------------------------
-- queue_positions  (brain-owned)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS queue_positions (
    snapshot_ts           INTEGER NOT NULL,
    market_id             TEXT NOT NULL,
    side                  TEXT NOT NULL CHECK(side IN ('long','short')),
    tick                  INTEGER NOT NULL,
    our_order_id          TEXT NOT NULL,
    queue_ahead_size_wei  TEXT NOT NULL,
    PRIMARY KEY(snapshot_ts, market_id, side, tick, our_order_id)
);

-- ---------------------------------------------------------------------------
-- run_manifests  (brain-owned) — INFRA-06 RUN_MANIFEST sidecar in relational form
-- ---------------------------------------------------------------------------
-- `parent_run_id` is a self-reference for mid-run knob-change chains; FK is
-- enforced only when the connection has `PRAGMA foreign_keys = ON`.
CREATE TABLE IF NOT EXISTS run_manifests (
    run_id                TEXT PRIMARY KEY,
    parent_run_id         TEXT REFERENCES run_manifests(run_id),
    started_at_iso        TEXT NOT NULL,
    mode                  TEXT NOT NULL CHECK(mode IN ('live','paper','backtest','ingest','screen')),
    strategy_version      TEXT NOT NULL,
    git_sha               TEXT NOT NULL,
    git_dirty             INTEGER NOT NULL CHECK(git_dirty IN (0,1)),
    market_id             TEXT NOT NULL,
    side                  TEXT NOT NULL CHECK(side IN ('long','short')),
    wallet_address_hash   TEXT NOT NULL,
    config_json           TEXT NOT NULL           -- full Pydantic knob tree, model_dump(mode='json')
);
CREATE INDEX IF NOT EXISTS ix_run_manifests_started_at ON run_manifests(started_at_iso);

-- ---------------------------------------------------------------------------
-- epoch_rewards  (brain-owned) — reward accrual + Merkle claim bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS epoch_rewards (
    epoch_end_ts         INTEGER NOT NULL,
    market_id            TEXT NOT NULL,
    our_accrued_pendle   REAL NOT NULL,
    claimed              INTEGER NOT NULL DEFAULT 0 CHECK(claimed IN (0,1)),
    claim_tx_hash        TEXT,
    PRIMARY KEY(epoch_end_ts, market_id)
);

-- ---------------------------------------------------------------------------
-- clo_history  (brain-owned) — DATA-06 /markets poll + fIndex for SCALE calib
-- ---------------------------------------------------------------------------
-- f_index_raw: decoded floatingIndex_raw from the fIndexOracle bytes26 payload,
-- polled at the same cadence as CLO by the /markets poller in plan 01-09. Required
-- by 01-11 SCALE calibration (two (clo, fIndex) pairs >= 1 day apart). Nullable
-- for historical rows that predate fIndex decoding; 01-09 populates on every poll.
CREATE TABLE IF NOT EXISTS clo_history (
    snapshot_ts       INTEGER NOT NULL,
    market_id         TEXT NOT NULL,
    clo_lower_thresh  REAL NOT NULL,
    clo_upper_thresh  REAL NOT NULL,
    f_index_raw       INTEGER,
    PRIMARY KEY(snapshot_ts, market_id)
);

-- ---------------------------------------------------------------------------
-- reward_budget_history  (brain-owned) — DATA-11 polled E_liq + B6 flag
-- ---------------------------------------------------------------------------
-- B6 pitfall flag: forward-only vs historically-reconstructed-from-current.
-- Phase-5 backtest MUST filter by data_source='polled' to avoid current-budget-
-- synthetic data leaking into historical P&L.
--
-- Anti-pattern 4 (ARCHITECTURE.md §9 / PITFALLS §A2): E_liq_per_epoch rebalances
-- dynamically per epoch. Downstream readers MUST read the most recent row ordered
-- by polled_at_utc DESC LIMIT 1. NEVER cache across polls.
--
-- Columns added by migration 0002 (vs original schema):
--   id AUTOINCREMENT (replaces snapshot_ts+market_id composite PK)
--   polled_at_utc  — wall-clock UTC ISO8601 (replaces snapshot_ts INTEGER)
--   chain_ts       — on-chain block timestamp from chain_time cache
--   run_id         — run_manifests.run_id (traceability)
CREATE TABLE IF NOT EXISTS reward_budget_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    polled_at_utc   TEXT NOT NULL,             -- ISO8601 UTC wall-clock
    chain_ts        INTEGER,                   -- on-chain block ts from cache
    market_id       TEXT NOT NULL,
    e_liq_per_epoch REAL NOT NULL,             -- PENDLE / epoch (live polled)
    long_budget     REAL NOT NULL,
    short_budget    REAL NOT NULL,
    run_id          TEXT NOT NULL,
    data_source     TEXT NOT NULL CHECK(data_source IN ('polled','synthetic_current'))
);
CREATE INDEX IF NOT EXISTS ix_reward_budget_market_polled
    ON reward_budget_history(market_id, polled_at_utc DESC);

-- ---------------------------------------------------------------------------
-- fill_model_fits  (brain-owned) — FILL-01 + FILL-05 + FILL-06 NHPP fit artifact
-- ---------------------------------------------------------------------------
-- One row per successful refit per (market, side). Primary key ordered so the
-- common "get latest fit" query is an index seek: (market_id, side, fit_window_end_ts DESC).
--
-- `covariate_whitelist`, `beta`, `beta_stderr` are JSON TEXT columns — matches
-- run_manifests.config_json pattern. `beta` has length 1 + len(covariate_whitelist)
-- because sm.add_constant prepends the intercept column; loader in Python validates.
--
-- fit_status:
--   ok       — IRLS converged, enough events per param, stderr bounded
--   degraded — fit-health gate failed (see fill_model.fit.py::_passes_health_gate)
--   stale    — emitted by calibration.py when fit is older than fit_warn_staleness_s
--              and still the most-recent; the row is updated via insert_fit_artifact
--              re-insert, not UPDATE, because single-writer discipline forbids UPDATE
--              from any other writer.
--
-- event_index_coverage: 'full' when market-trades has no null eventIndex in the
-- fit window; 'degraded' when the queue tracker ran in null-eventIndex graceful-
-- degrade mode (RESEARCH §Assumption A3).

CREATE TABLE IF NOT EXISTS fill_model_fits (
    run_id              TEXT NOT NULL,
    fit_window_start_ts INTEGER NOT NULL,
    fit_window_end_ts   INTEGER NOT NULL,
    market_id           TEXT NOT NULL,
    side                TEXT NOT NULL CHECK(side IN ('long','short')),
    covariate_whitelist TEXT NOT NULL,
    beta                TEXT NOT NULL,
    beta_stderr         TEXT NOT NULL,
    log_likelihood      REAL NOT NULL,
    deviance            REAL NOT NULL,
    aic                 REAL NOT NULL,
    n_observations      INTEGER NOT NULL,
    converged           INTEGER NOT NULL CHECK(converged IN (0,1)),
    fit_status          TEXT NOT NULL CHECK(fit_status IN ('ok','degraded','stale')),
    gof_ks_pval         REAL,
    gof_lr_vs_null      REAL,
    event_index_coverage TEXT NOT NULL DEFAULT 'full'
        CHECK(event_index_coverage IN ('full','degraded')),
    created_at          INTEGER NOT NULL,
    PRIMARY KEY(market_id, side, fit_window_end_ts)
);

CREATE INDEX IF NOT EXISTS ix_fill_model_fits_market_side_end
    ON fill_model_fits(market_id, side, fit_window_end_ts DESC);

-- ---------------------------------------------------------------------------
-- loss_grid_artifacts  (brain-owned) — LOSS-01 + LOSS-02 empirical loss-grid artifact
-- ---------------------------------------------------------------------------
-- Single writer: brain.state.writers.loss_grid_artifacts.
-- Read by:       brain.loss_model.expected_loss, brain.sizer.optimizer (Plan 03-03).
--
-- One row per successful refit per (market, side). Primary key ordered so the
-- common "get latest grid" query is an index seek:
--   (market_id, side, window_end_ts DESC).
--
-- depth_bucket_edges, tau_bucket_edges_days, cells_json are JSON TEXT columns
-- (matches run_manifests.config_json + fill_model_fits.beta JSON-as-TEXT pattern).
-- cells_json is `list[LossGridCell.model_dump()]`; deserialised via json.loads in
-- get_latest_loss_grid.
--
-- fit_status:
--   ok       — full coverage, all cells have n_samples >= min_samples_per_cell.
--   degraded — half or more grid cells sparse, OR fit raised on no_data.
--   stale    — emitted by expected_loss when fit_age_s > fit_warn_staleness_s
--              and still the most-recent; row is updated via insert_loss_grid_artifact
--              re-insert (single-writer discipline forbids UPDATE from any other writer).
--
-- event_index_coverage: 'full' when every replay fill had a non-null fill_event_index,
-- 'degraded' when any fill in the window lacked eventIndex (degraded-mode replay).

CREATE TABLE IF NOT EXISTS loss_grid_artifacts (
    run_id                TEXT NOT NULL,
    market_id             TEXT NOT NULL,
    side                  TEXT NOT NULL CHECK(side IN ('long','short')),
    window_start_ts       INTEGER NOT NULL,
    window_end_ts         INTEGER NOT NULL,
    fit_status            TEXT NOT NULL CHECK(fit_status IN ('ok','degraded','stale')),
    depth_bucket_edges    TEXT NOT NULL,   -- JSON list[float]
    tau_bucket_edges_days TEXT NOT NULL,   -- JSON list[float]
    cells_json            TEXT NOT NULL,   -- JSON list[LossGridCell]
    event_index_coverage  TEXT NOT NULL DEFAULT 'full'
        CHECK(event_index_coverage IN ('full','degraded')),
    created_at            INTEGER NOT NULL,
    PRIMARY KEY (market_id, side, window_end_ts)
);

CREATE INDEX IF NOT EXISTS ix_loss_grid_artifacts_market_side_end
    ON loss_grid_artifacts(market_id, side, window_end_ts DESC);

-- ---------------------------------------------------------------------------
-- competition_history  (brain-owned) — REWARD-02 Σ_others tracker (Plan 03-02)
-- ---------------------------------------------------------------------------
-- Single writer: brain.state.writers.competition_history.
-- Read by:       brain.reward_model.r_capped, brain.sizer.optimizer (Plan 03-03).
--
-- One row per CompetitionTracker.run_one_cycle per market. data_source enum:
--   'live'                     — REST + parquet both healthy
--   'fallback_parquet_only'    — N consecutive REST failures; q_me estimated
--                                from state.open_orders + Σ_others read from
--                                parquet.order_book_raw (AMM share excluded
--                                per T-03-06).
--
-- AMM share is EXCLUDED by reading parquet.order_book_raw (NOT order_book_combined)
-- — AMMs do not compete for LO Liquidity Rewards.
CREATE TABLE IF NOT EXISTS competition_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    polled_at_utc       TEXT NOT NULL,
    chain_ts            INTEGER,
    market_id           TEXT NOT NULL,
    q_me_pendle         REAL NOT NULL,
    sigma_others_pendle REAL NOT NULL,
    data_source         TEXT NOT NULL CHECK(data_source IN ('live','fallback_parquet_only')),
    run_id              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_competition_history_market_polled
    ON competition_history (market_id, polled_at_utc DESC);

-- ---------------------------------------------------------------------------
-- market_reward_calibration  (brain-owned) — LOCKED D-01 operator-manual E_liq source
-- ---------------------------------------------------------------------------
-- Single writer: brain.state.writers.market_reward_calibration.
-- Read by:       brain.reward_model.r_capped, brain.sizer.optimizer (Plan 03-03).
--
-- LOCKED D-01 (2026-04-24) per user decision: supersedes ELiqPoller's polling
-- of liquidityRewardPerEpoch / longBudget / shortBudget from GET /markets — those
-- fields are absent from the live API. Operator pastes values from Pendle docs /
-- dApp UI / team announcements via the calibrate CLI subcommand.
--
-- data_source CHECK enforces ONLY 'operator' — single lineage marker.
-- See [[e-liq-per-epoch-source-decision]] for the full evidence log and
-- [[market-reward-calibration-operator-workflow]] for the runbook.
CREATE TABLE IF NOT EXISTS market_reward_calibration (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id               TEXT NOT NULL,
    e_liq_per_epoch_pendle  REAL NOT NULL CHECK(e_liq_per_epoch_pendle >= 0.0),
    long_side_split         REAL NOT NULL CHECK(long_side_split BETWEEN 0.0 AND 1.0),
    short_side_split        REAL NOT NULL CHECK(short_side_split BETWEEN 0.0 AND 1.0),
    calibrated_at_utc       TEXT NOT NULL,
    data_source             TEXT NOT NULL CHECK(data_source = 'operator'),
    source                  TEXT NOT NULL CHECK(source IN ('dapp_ui','team_statement','pendle_docs')),
    run_id                  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_market_reward_calibration_market_calibrated
    ON market_reward_calibration (market_id, calibrated_at_utc DESC);
