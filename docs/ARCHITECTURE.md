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

    %% DuckDB analytical layer (01-07 INFRA-04)
    brain_duckdb_setup -- "sqlite_scanner read-only attach" --> state_clo
    brain_duckdb_setup -- "reads views.sql DDL at runtime" --> brain_duckdb_setup

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
```

## What's declared in `docs/architecture.yml`

The YAML manifest enumerates:

- **2 process nodes** — `brain` (Python), `hands` (TypeScript).
- **~22 module nodes** — every `.py` under `python/src/boros_brain/` and every
  `.ts` under `ts/src/boros_hands/` that exists today.
- **8 storage nodes** — one per SQLite table (`open_orders`, `decisions`,
  `tx_receipts`, `queue_positions`, `run_manifests`, `epoch_rewards`,
  `clo_history`, `reward_budget_history`).
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
