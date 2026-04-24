---
status: Phase 1 seed
last_updated: 2026-04-23
---

# Boros Bot — Architecture

This is the single human-facing map of the Boros bot. It shows every long-lived
process, every module that already exists (plans 01-01 / 01-02 / 01-03), the
SQLite state spine, the ZMQ cmd/events bus, the RUN_MANIFEST trail, and every
external dependency the bot currently reaches.

The machine-readable companion is `docs/architecture.yml` — `scripts/architecture_lint.py`
parses that file at every commit and fails the commit if the declared manifest
drifts from what the source tree actually contains. The two files MUST move
together. If you add a module, add its node here AND in `architecture.yml` in
the same commit (or the pre-commit hook blocks you).

> **Engineering Protocol #2.** Before changing code, open this diagram, trace
> upstream (what feeds the node you're changing) and downstream (what the node
> feeds), and enumerate the blast radius in your plan or PR description. A
> change that cannot name its affected nodes has not been thought through.

## System Diagram (Phase 1 seed)

```mermaid
flowchart TB
    subgraph ext["External dependencies"]
        ext_boros["ext.boros_rest<br/>api.boros.finance/open-api/v1"]
        ext_rpc["ext.arbitrum_rpc<br/>arb1.arbitrum.io/rpc"]
        ext_hist["ext.boros_historical_data<br/>historical-data.boros.finance"]
    end

    subgraph supervision["Process supervision (launchd, 01-06)"]
        launchd_brain["launchd.brain<br/>com.boros.brain.plist<br/>KeepAlive + ThrottleInterval=30"]
        launchd_hands["launchd.hands<br/>com.boros.hands.plist<br/>KeepAlive + ThrottleInterval=30"]
        keychain["macos.keychain<br/>login Keychain<br/>boros-bot-dotenvx-key"]
        brain_wrapper["scripts.boros_brain_wrapper<br/>boros-brain-wrapper.sh"]
        hands_wrapper["scripts.boros_hands_wrapper<br/>boros-hands-wrapper.sh"]
        no_plain_keys["scripts.no_plain_keys<br/>no_plain_keys.py<br/>pre-commit hook"]
        no_time_time["scripts.no_time_time_lint<br/>no_time_time_lint.py<br/>pre-commit hook (INFRA-14)"]
    end

    subgraph brain["brain — Python process (asyncio, 1 Hz)"]
        brain_main["main.py<br/>entrypoint"]
        brain_cfg_loader["config/loader.py<br/>load_config"]
        brain_cfg_schema["config/schema.py<br/>BotConfig (Pydantic v2)"]
        brain_manifest_writer["manifest/writer.py<br/>build_run_manifest, write_manifest"]
        brain_manifest_schema["manifest/schema.py<br/>RunManifest"]
        brain_log_setup["logging/structlog_setup.py<br/>configure_logging, get_logger"]
        brain_log_schema["logging/schema.py<br/>LogRecord"]
        brain_log_redaction["logging/redaction.py<br/>redact_sensitive (01-06)"]
        brain_data_rpc["data/rpc_client.py<br/>make_arbitrum_rpc, get_latest_block_timestamp (01-07)"]
        brain_data_chain_time["data/chain_time.py<br/>ChainTimeCache, now_cached, startup_check,<br/>drift_monitor_tick (INFRA-14, 01-07)"]
        brain_data_rest_client["data/rest_client.py<br/>make_boros_rest_client, BorosApiError (01-09)"]
        brain_data_findex_reader["data/findex_reader.py<br/>FIndexReader, decode_findex_bytes,<br/>fIndex_display (DATA-07, 01-09)"]
        brain_data_poller_schemas["data/poller/schemas.py<br/>MarketsResponse, Market, MarketConfig (01-09)"]
        brain_data_poller_markets["data/poller/markets_poller.py<br/>MarketsPoller, run_markets_poller (DATA-06, 01-09)"]
        brain_data_poller_e_liq["data/poller/e_liq_poller.py<br/>ELiqPoller (DATA-11, 01-10)<br/>NO cross-poll cache — PITFALLS §A2"]
        brain_duckdb_setup["duckdb_layer/setup.py<br/>open_analytical_conn (INFRA-04, 01-07)<br/>ANALYTICAL ONLY — not on hot path"]
        brain_bus_cmd["bus/cmd.py<br/>CmdBus (ZMQ PUSH)"]
        brain_bus_events["bus/events.py<br/>EventBus (ZMQ PUB/SUB)"]
        brain_bus_heartbeat["bus/heartbeat.py<br/>HeartbeatMonitor"]
        brain_bus_messages["bus/messages.py<br/>PlaceCmd / CancelCmd / KillCmd / Heartbeat / LostSibling / RunManifestAnnounce"]
        brain_state_db["state/db.py<br/>open_connection (WAL, chmod 600)"]
        brain_writers_decisions["state/writers/decisions.py"]
        brain_writers_queue["state/writers/queue_positions.py"]
        brain_writers_runmanifests["state/writers/run_manifests.py"]
        brain_writers_epoch["state/writers/epoch_rewards.py"]
        brain_writers_clo["state/writers/clo_history.py"]
        brain_writers_budget["state/writers/reward_budget_history.py"]
    end

    subgraph hands["hands — TypeScript process (Node 24)"]
        hands_main["main.ts<br/>entrypoint"]
        hands_logger["logger.ts<br/>configureHandsLogger, log"]
        hands_bus_cmd["bus/cmd_listener.ts<br/>CmdListener"]
        hands_bus_events["bus/event_publisher.ts<br/>EventPublisher"]
        hands_bus_heartbeat["bus/heartbeat.ts<br/>HeartbeatMonitor"]
        hands_bus_messages["bus/messages.ts<br/>Zod mirror"]
        hands_state_writer["state/sqlite_writer.ts<br/>openHandsDb, upsertOpenOrder, insertTxReceipt"]
    end

    subgraph state[("state.sqlite (WAL, chmod 600)")]
        state_open_orders[("open_orders")]
        state_decisions[("decisions")]
        state_tx_receipts[("tx_receipts")]
        state_queue[("queue_positions")]
        state_runmanifests[("run_manifests")]
        state_epoch[("epoch_rewards")]
        state_clo[("clo_history")]
        state_budget[("reward_budget_history")]
    end

    subgraph logs_dir["logs/ (JSON, run_id-stamped)"]
        logs_brain["brain-*.log.jsonl"]
        logs_hands["hands-*.log.jsonl"]
        logs_manifest["{run_id}.manifest.json (sidecar)"]
    end

    %% supervision wiring (01-06)
    launchd_brain --> brain_wrapper
    launchd_hands --> hands_wrapper
    brain_wrapper -- "security find-generic-password" --> keychain
    hands_wrapper -- "security find-generic-password" --> keychain
    brain_wrapper -- "exec dotenvx run -- uv run python -m boros_brain.main" --> brain_main
    hands_wrapper -- "exec dotenvx run -- pnpm start:hands" --> hands_main

    %% redaction processor (01-06) — node declared in brain subgraph above
    brain_log_redaction -- "extra_processor before JSONRenderer" --> brain_log_setup

    %% chain-time + RPC client (01-07 INFRA-14)
    brain_data_chain_time -- "get_latest_block_timestamp()" --> brain_data_rpc
    brain_data_rpc -- "AsyncHTTPProvider(rpc_url_arbitrum)" --> ext_rpc
    brain_data_chain_time -- "halt_callback → KILL lane on drift > 30s" --> brain_bus_cmd
    no_time_time -- "pre-commit: rejects time.time() in brain/{decision,data,screener}" --> brain

    %% DATA-11 E_liq poller (01-10)
    brain_data_poller_e_liq -- "GET /markets E_liq_per_epoch" --> brain_data_rest_client
    brain_data_poller_e_liq -- "get_chain_time_cached() chain_ts" --> brain_data_chain_time
    brain_data_poller_e_liq -- "insert_reward_budget_row one row/cycle/market" --> brain_writers_budget
    brain_writers_budget -- writes --> state_budget

    %% DATA-06 /markets poller + DATA-07 fIndexOracle reader (01-09)
    brain_data_poller_markets -- "make_boros_rest_client GET /markets" --> brain_data_rest_client
    brain_data_rest_client -- "httpx.AsyncClient" --> ext_boros
    brain_data_poller_markets -- "MarketsResponse.model_validate_json" --> brain_data_poller_schemas
    brain_data_poller_markets -- "now_cached() snapshot_ts" --> brain_data_chain_time
    brain_data_poller_markets -- "FIndexReader.get_latest_fIndex()" --> brain_data_findex_reader
    brain_data_findex_reader -- "eth_call getLatestFIndex bytes32" --> brain_data_rpc
    brain_data_poller_markets -- "insert_clo_history on change only" --> brain_writers_clo

    %% DuckDB analytical layer (01-07 INFRA-04)
    brain_duckdb_setup -- "sqlite_scanner read-only attach" --> state_clo
    brain_duckdb_setup -- "reads views.sql DDL at runtime" --> brain_duckdb_setup

    %% DATA-01..04 NDJSON ingesters (01-08)
    ingester_cli["data/ingester/cli.py<br/>main (--kind dispatch, RUN_MANIFEST)"]
    ingester_base["data/ingester/base.py<br/>write_partitioned_parquet, IngestResult"]
    ingester_schemas["data/ingester/schemas.py<br/>MARKET_TRADES_SCHEMA etc."]
    ingester_mt["data/ingester/market_trades.py<br/>ingest_market_trades (DATA-01)"]
    ingester_ob["data/ingester/order_book.py<br/>ingest_order_book_raw/combined (DATA-02)<br/>assert_amm_conservation (DATA-05, 01-10)"]
    ingester_exc["data/ingester/exceptions.py<br/>AMMConservationError (DATA-05, 01-10)"]
    ingester_apr["data/ingester/underlying_apr.py<br/>ingest_underlying_apr (DATA-03)"]
    ingester_smd["data/ingester/settlement_md.py<br/>ingest_settlement_md (DATA-04)"]

    parquet_mt[("parquet/market_trades<br/>market_id / year_month")]
    parquet_ob_raw[("parquet/order_book_raw<br/>market_id / snapshot_ts")]
    parquet_ob_comb[("parquet/order_book_combined<br/>market_id / tick_size / snapshot_ts")]
    parquet_apr[("parquet/underlying_apr<br/>exchange / year_month")]
    parquet_sett[("parquet/settlement<br/>market_id / year_month")]
    parquet_md[("parquet/market_data<br/>market_id / year_month")]

    ingester_cli --> ingester_mt
    ingester_cli --> ingester_ob
    ingester_cli --> ingester_apr
    ingester_cli --> ingester_smd
    ingester_cli -- "write_manifest RUN_MANIFEST" --> brain_manifest_writer
    ingester_mt --> ingester_base
    ingester_ob --> ingester_base
    ingester_apr --> ingester_base
    ingester_smd --> ingester_base
    ingester_mt -- reads --> ingester_schemas
    ingester_ob -- reads --> ingester_schemas
    ingester_apr -- reads --> ingester_schemas
    ingester_smd -- reads --> ingester_schemas
    ingester_ob -- "raise AMMConservationError (DATA-05 / PITFALLS §B3)" --> ingester_exc
    ingester_mt -- writes --> parquet_mt
    ingester_ob -- writes --> parquet_ob_raw
    ingester_ob -- writes --> parquet_ob_comb
    ingester_apr -- writes --> parquet_apr
    ingester_smd -- writes --> parquet_sett
    ingester_smd -- writes --> parquet_md
    brain_duckdb_setup -- "market_trades VIEW" --> parquet_mt
    brain_duckdb_setup -- "order_book_raw VIEW" --> parquet_ob_raw
    brain_duckdb_setup -- "order_book_combined VIEW" --> parquet_ob_comb
    brain_duckdb_setup -- "underlying_apr VIEW" --> parquet_apr
    brain_duckdb_setup -- "settlement VIEW" --> parquet_sett
    brain_duckdb_setup -- "market_data VIEW" --> parquet_md
    ingester_cli -- "NDJSON --src from" --> ext_hist

    %% A6 historical budget spike (01-10 — one-shot script, not a long-lived task)
    spike_a6["scripts/probe_historical_budget.py<br/>A6 spike — distributor event probe<br/>(one-shot operator command)"]
    verdict_a6[("var/reports/a6_historical_budget_verdict.json<br/>feasible/infeasible verdict")]
    spike_a6 -- "eth_getLogs distributor events (live only)" --> ext_rpc
    spike_a6 -- writes --> verdict_a6

    %% DATA-08 screener metrics (01-11 Task 1)
    screener_metrics["screener/metrics.py<br/>compute_inter_arrival_cv, compute_realized_vol,<br/>compute_reversal_count, compute_depth_at_clo_edge,<br/>compute_outside_range_wall_ratio, compute_days_to_maturity<br/>(DATA-08, 01-11)"]
    screener_metrics -- "reads market_trades (CV, vol, reversal)" --> parquet_mt
    screener_metrics -- "reads order_book_combined (depth, wall ratio)" --> parquet_ob_comb
    screener_metrics -- "reads clo_lower_thresh/clo_upper_thresh" --> state_clo

    %% DATA-08 SCALE calibration (01-11 Task 2)
    screener_scale_cal["screener/scale_calibration.py<br/>calibrate_scale, get_calibration_pairs<br/>(A8 mitigation: per-market SCALE from 2 clo_history rows, 01-11)"]
    screener_scale_cal -- "reads snapshot_ts/clo_lower_thresh/f_index_raw" --> state_clo
    screener_scale_cal -- "fIndexOracle bytes decoded by poller, stored as f_index_raw" --> brain_data_rpc

    %% DATA-08 filter + report + CLI (01-11 Task 3)
    screener_filter["screener/filter.py<br/>apply_screener_filters — 6 filters + A8 wall flag<br/>T-01-11-03: shortlist cap at 4 by r_apr_potential rank<br/>(DATA-08, 01-11)"]
    screener_report["screener/report.py<br/>write_screener_metrics_report<br/>(DATA-08, 01-11)"]
    screener_cli["screener/cli.py<br/>main, run_screener<br/>--run DATA-08, --economics-gate DATA-09<br/>RUN_MANIFEST-first (01-11 + 01-12)"]
    screener_out[("var/reports/screener_metrics.json<br/>shortlist + full metric tree")]
    screener_filter -- "calls all 6 compute_* fns" --> screener_metrics
    screener_filter -- "get_calibration_pairs + calibrate_scale (non-blocking)" --> screener_scale_cal
    screener_filter -- "reads clo_lower_thresh/clo_upper_thresh" --> state_clo
    screener_filter -- "reads e_liq_per_epoch for r_apr_potential ranking" --> state_budget
    screener_report -- writes --> screener_out
    screener_cli -- "apply_screener_filters" --> screener_filter
    screener_cli -- "write_screener_metrics_report" --> screener_report
    screener_cli -- "build_run_manifest + write_manifest (PROTO-01)" --> brain_manifest_writer

    %% DATA-09 economics kill-switch (01-12 Task 1)
    screener_economics_gate["screener/economics_gate.py<br/>compute_r_apr_on_collateral_pendle<br/>run_economics_gate, ConfigError, ProjectHalt<br/>(DATA-09, 01-12)"]
    screener_kill_report["screener/kill_report.py<br/>write_kill_report<br/>(T-01-12-04, 01-12)"]
    kill_report_template[("docs/kill-report-template.md<br/>template for halt artifact")]
    kill_report_out[("docs/kill-report-YYYYMMDD.md<br/>halt artifact: R_apr table + knob tree")]
    economics_gate_out[("var/reports/economics_gate.json<br/>per-market DATA-09 decisions")]
    screener_cli -- "--economics-gate: run_economics_gate" --> screener_economics_gate
    screener_economics_gate -- "load_raw_yaml + load_config" --> brain_cfg_loader
    screener_economics_gate -- "reads r_apr_potential for each filter_pass market" --> screener_out
    screener_economics_gate -- "calls write_kill_report on empty shortlist" --> screener_kill_report
    screener_economics_gate -- writes --> economics_gate_out
    screener_kill_report -- "reads template" --> kill_report_template
    screener_kill_report -- writes --> kill_report_out

    %% DATA-10 daily re-screen (01-12 Task 2)
    screener_rescreen["screener/rescreen.py<br/>run_daily_rescreen<br/>ingest -> screener -> economics gate -> diff<br/>(DATA-10, 01-12)"]
    launchd_rescreen["launchd.com.boros.rescreen<br/>CalendarInterval 03:00 UTC<br/>KeepAlive=false (one-shot daily)"]
    rescreen_diff_out[("var/reports/rescreen_diff.json<br/>new_entrants + dropped + unchanged")]
    launchd_rescreen -- "python -m boros_brain.screener.rescreen" --> screener_rescreen
    screener_rescreen -- "run_screener (DATA-08 stage)" --> screener_cli
    screener_rescreen -- "run_economics_gate (DATA-09 stage)" --> screener_economics_gate
    screener_rescreen -- writes --> rescreen_diff_out

    %% brain wiring
    brain_main --> brain_cfg_loader --> brain_cfg_schema
    brain_main --> brain_manifest_writer --> brain_manifest_schema
    brain_manifest_writer -- reads model_dump(mode='json') --> brain_cfg_schema
    brain_manifest_writer --> brain_writers_runmanifests
    brain_writers_runmanifests -- writes --> state_runmanifests
    brain_writers_decisions -- writes --> state_decisions
    brain_writers_queue -- writes --> state_queue
    brain_writers_epoch -- writes --> state_epoch
    brain_writers_clo -- writes --> state_clo
    brain_writers_budget -- writes --> state_budget
    brain_writers_decisions --> brain_state_db
    brain_writers_queue --> brain_state_db
    brain_writers_runmanifests --> brain_state_db
    brain_writers_epoch --> brain_state_db
    brain_writers_clo --> brain_state_db
    brain_writers_budget --> brain_state_db
    brain_main --> brain_log_setup --> brain_log_schema
    brain_log_setup --> logs_brain
    brain_manifest_writer --> logs_manifest
    brain_main --> brain_bus_cmd
    brain_main --> brain_bus_events
    brain_main --> brain_bus_heartbeat
    brain_bus_cmd --> brain_bus_messages
    brain_bus_events --> brain_bus_messages
    brain_bus_heartbeat --> brain_bus_messages

    %% hands wiring
    hands_main --> hands_logger --> logs_hands
    hands_main --> hands_bus_cmd --> hands_bus_messages
    hands_main --> hands_bus_events --> hands_bus_messages
    hands_main --> hands_bus_heartbeat --> hands_bus_messages
    hands_main --> hands_state_writer
    hands_state_writer -- writes --> state_open_orders
    hands_state_writer -- writes --> state_tx_receipts

    %% cross-process ZMQ edges
    brain_bus_cmd -- "ZMQ PUSH ipc:///tmp/boros.cmd" --> hands_bus_cmd
    brain_bus_cmd -- "ZMQ PUSH ipc:///tmp/boros.cmd.kill (priority lane)" --> hands_bus_cmd
    hands_bus_events -- "ZMQ PUB ipc:///tmp/boros.events.hands" --> brain_bus_events
    brain_bus_events -- "ZMQ PUB ipc:///tmp/boros.events.brain" --> hands_bus_events

    %% external edges (stubs for the pollers + readers that land in later Phase-1 plans)
    brain -- "HTTPS GET /markets, /epoch-rewards" --> ext_boros
    brain -- "eth_call fIndexOracle" --> ext_rpc
    brain -- "NDJSON download market-trades, order-book" --> ext_hist

    %% Phase 2 Fill Model (Plans 02-01 + 02-02 + 02-03 + 02-04)
    subgraph fill_model["Fill Model (Phase 2, Plans 02-01/02/03/04)"]
        fill_features_mod["fill_model/features.py<br/>build_features_table (FILL-02)"]
        fill_config_mod["fill_model/config.py<br/>FillModelConfig (11 knobs)"]
        fill_constants_mod["fill_model/constants.py<br/>ALLOWED_COVARIATES + DEFAULT_*"]
        parquet_fill_features[("parquet/fill_features<br/>market_id / side")]
        fill_queue_tracker["fill_model/queue_tracker.py<br/>QueueTracker + compute_drift_diagnostic (FILL-03)"]
        fill_amm_consumption["fill_model/amm_consumption.py<br/>compute_amm_share_timeseries + assert_epoch_conservation (FILL-04)"]
        fill_schemas["fill_model/schemas.py<br/>ReplayResult + EpochFlowSnapshot +<br/>AMMConsumptionIdentityError +<br/>FitArtifact + PredictInput/Output +<br/>FillModelStaleFeatureError + FillModelNoFreshFitError"]
        FitMod["fill_model/fit.py<br/>fit_market_side (FILL-01)"]
        PredictMod["fill_model/predict.py<br/>predict() SYNC (FILL-05)"]
        Artifact["fill_model/artifact.py<br/>write_fit_artifact"]
        FillFitsWriter["state/writers/fill_model_fits.py<br/>insert_fit_artifact + get_latest_fit"]
        StateFillFits[("state.fill_model_fits<br/>SQLite table — PK market/side/end_ts")]
        ParquetFitArtifacts[("parquet/fill_model_artifacts<br/>market_id / side / window_end_ts")]

        fill_features_mod -->|writes| parquet_fill_features
        fill_config_mod -->|reads| fill_constants_mod
        fill_queue_tracker -->|calls| fill_amm_consumption
        fill_queue_tracker -->|uses| fill_schemas
        fill_amm_consumption -->|uses| fill_schemas
        FitMod -->|calls| Artifact
        Artifact -->|calls single-writer| FillFitsWriter
        Artifact -->|writes parquet-first| ParquetFitArtifacts
        FillFitsWriter -->|writes| StateFillFits
        PredictMod -->|reads| FillFitsWriter
        parquet_fill_features -->|consumed by| FitMod
        CalibrationMod["fill_model/calibration.py<br/>gof_rosenblatt + bootstrap_gof_threshold + run_calibration (FILL-06)"]
        RefitLoopMod["fill_model/refit_loop.py<br/>refit_once (async boot) + run_fill_model_refit_loop"]
        ReportMod["fill_model/report.py<br/>write_fill_model_report"]
        CliMod["fill_model/cli.py + __main__.py<br/>fit/predict/calibration-report/force-degrade (MANIFEST-FIRST)"]
        CalibrationMod -->|calls| FitMod
        CalibrationMod -->|calls| PredictMod
        CalibrationMod -->|reads| FillFitsWriter
        RefitLoopMod -->|calls| fill_features_mod
        RefitLoopMod -->|calls| FitMod
        ReportMod -->|reads| FillFitsWriter
        CliMod -->|calls| RefitLoopMod
        CliMod -->|calls| PredictMod
        CliMod -->|calls| ReportMod
        CliMod -->|calls| FitMod
    end

    parquet_mt -->|"DuckDB market_trades view"| fill_features_mod
    parquet_ob_comb -->|"DuckDB order_book_combined view"| fill_features_mod
    parquet_apr -->|"DuckDB underlying_apr view"| fill_features_mod
    state_clo -->|"sqlite_scanner read-only"| fill_features_mod
    fill_features_mod -->|"open_analytical_conn"| brain_duckdb_setup
    brain_cfg_schema -->|"BotConfig.fill_model attach-point"| fill_config_mod
    parquet_mt -->|"eventIndex-ordered replay"| fill_queue_tracker
    parquet_ob_raw -->|"hourly anchors"| fill_queue_tracker
    parquet_ob_raw -->|"per-tick raw size"| fill_amm_consumption
    parquet_ob_comb -->|"per-tick combined size"| fill_amm_consumption
```

### Phase 2 Fill Model (Plans 02-01 + 02-02 + 02-03 + 02-04)

The fill model consumes Phase 1's data pipeline outputs through a DuckDB-joined
feature table. `build_features_table` (in `brain.fill_model.features`) produces
per-(market, side, bin) rows with 5 covariates: `basis_spread`, `imbalance`,
`sin_settlement`, `cos_settlement`, `ewma_vol`. The EWMA uses a strict
left-closed window (`ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING`) — no
look-ahead (T-02-F-02). `FillModelConfig` carries 11 knobs; all auto-surface
in RUN_MANIFEST via reflection (T-02-R-01).

**Plan 02-02 additions:** `QueueTracker` runs a tri-track replay
(pessimistic / realized / optimistic) on `(blockTimestamp, eventIndex)`-ordered
market-trades, reconciling against hourly `order_book_raw` snapshots. Drift
diagnostic and bracket-width warnings are emitted as
`fill_model.queue_drift_reconciliation` and `fill_model.bracket_width_warn`
log events. `AMMConsumption` is the runtime analogue of Phase 1's `DATA-05`
ingest-time assertion — per-tick `amm_share = max(combined - raw, 0.0)` and a
per-epoch flow-identity check that raises `AMMConsumptionIdentityError` on
violation. PITFALLS §B1 (queue-drift blindness) and §B3 (AMM double-count) are
defused.

**Plan 02-03 additions:** `fit_market_side` (in `brain.fill_model.fit`) runs
`statsmodels.GLM(Poisson, log, exposure=bin_duration_s)` on feature rows from
Plan 02-01's `build_features_table`. The `FitArtifact` is written atomically
via `brain.fill_model.artifact.write_fit_artifact` — parquet sidecar first (for
orphan-tolerance), then a SQLite row via `brain.state.writers.fill_model_fits.
insert_fit_artifact` (single-writer-per-table; only module allowed to INSERT).
`brain.fill_model.predict` is the sync entry point Phase 4's DecisionEngine
calls at 1 Hz; NaN covariates raise `FillModelStaleFeatureError` (never silent
fallback; see [[known-issues-nan-covariate-silent-fallback-do-not]]); stale fits
raise `FillModelNoFreshFitError`. The `fill_model_fits` SQLite schema is
installed via Alembic migration `0003_fill_model_fits`.

**Plan 02-04 additions:** `calibration.py` implements Rosenblatt's time-change
theorem — the KS statistic between integrated-compensator inter-arrival gaps and
Exp(1) (`scipy.stats.kstest`). `bootstrap_gof_threshold` derives the 5th-
percentile LR threshold from 100 in-sample resamples rather than an
intuition-picked constant (PITFALL #8). `fill_model.fit_degraded` is emitted
when `gof_ks_pval < gof_ks_pval_threshold` — grepp-able by `run_id` and
surfaced by `force-degrade` smoke test. `refit_loop.py` exposes `refit_once`
(async coroutine awaited at brain boot to guarantee an artifact before the 1 Hz
loop starts) and `run_fill_model_refit_loop` (15-min cadence asyncio task spawned
from `brain.main.run()`). `cli.py` / `__main__.py` provide the operator CLI
(`python -m boros_brain.fill_model fit|predict|calibration-report|force-degrade`)
with MANIFEST-FIRST boot (PROTO-01).

See [[fill-model-library-decision-tick-vs-statsmodels]], [[covariate-selection-v05]],
[[queue-tracker-algorithm-v05]], [[amm-consumption-model-v05]],
[[nhpp-log-linear-glm-fit-procedure]], [[fill-model-predict-contract]],
[[fill-model-goodness-of-fit-rosenblatt-time-change]], and
[[rolling-14-day-refit-cadence-and-staleness]].

## What's declared in `docs/architecture.yml`

The YAML manifest enumerates:

- **2 process nodes** — `brain` (Python), `hands` (TypeScript).
- **~22 module nodes** — every `.py` under `python/src/boros_brain/` and every
  `.ts` under `ts/src/boros_hands/` that exists today.
- **10 storage nodes** — one per SQLite table (`open_orders`, `decisions`,
  `tx_receipts`, `queue_positions`, `run_manifests`, `epoch_rewards`,
  `clo_history`, `reward_budget_history`, `fill_model_fits`) plus parquet
  artifact store (`parquet.fill_model_artifacts`).
- **N config_knob nodes** — one per leaf of `BotConfig` / `StrategyConfig` /
  `ExecutionConfig` / `DataConfig` / `InfraConfig` / `ScreenerConfig`. Every
  leaf that exists in the Pydantic schema is a node here too. Adding a knob
  without declaring it fails the lint.
- **3 external dependency nodes** — `ext.boros_rest`, `ext.arbitrum_rpc`,
  `ext.boros_historical_data`.

The `edges:` list carries every link established by plans 01-01 / 01-02 / 01-03
so far: `calls`, `reads`, `writes`, `emits-event`, `subscribes-to`. Config-knob
`depends-on-config` edges are sparse at Phase 1 because most consumers land in
Phase 2+ — they are added in-commit by the plans that introduce the consumers.

## How to extend this diagram

When a Phase 2+ plan lands a new module or config knob, in the same commit
that adds the source file:

1. Add the node to `docs/architecture.yml` under `nodes:` (with `type:`,
   `process:`, `path:`, and `public_functions:` if applicable).
2. Add the `edges:` entries pointing into and out of the new node (every
   `calls`, `reads`, `writes`, `emits-event`, `depends-on-config` relationship
   it participates in).
3. Update the Mermaid block above — add the node to the correct subgraph,
   draw the edges, keep the labelling consistent with the existing nodes.
4. Run `python scripts/architecture_lint.py` locally before committing — the
   pre-commit hook will also run it.

The sole documented exception to this rule is the bootstrap commit that first
creates `docs/architecture.yml` itself. See `docs/override-log.md`.

## Related protocols

- Engineering Protocol #1 — LLM Wiki. Every research / decision / postmortem
  markdown cites a `[[wiki-link]]` at least once. Enforced by
  `scripts/wiki_cite_lint.py`.
- Engineering Protocol #3 — RUN_MANIFEST. Every run emits a manifest with the
  full knob tree on the first log record + sidecar JSON. Enforced by the
  Pydantic-reflection round-trip test in `python/tests/test_manifest_contains_all_knobs.py`.
