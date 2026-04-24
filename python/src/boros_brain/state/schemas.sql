-- Canonical SQLite schema for the boros v0.5 state spine (INFRA-03).
--
-- Source of truth: this file. The Alembic migration 0001_initial_8_tables replays
-- these statements in order; any schema change lands here first and gets a new
-- Alembic revision in the same commit.
--
-- Ownership map (enforced by scripts/sqlite_writer_lint.py):
--   hands (TS sqlite_writer.ts):  open_orders, tx_receipts
--   brain (Python state/writers/<table>.py): decisions, queue_positions,
--     run_manifests, epoch_rewards, clo_history, reward_budget_history
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
