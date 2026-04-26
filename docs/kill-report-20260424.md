# Project Halt: Economics Kill-Switch Empty Shortlist

**Timestamp (UTC):** 2026-04-24T11:13:23.319884+00:00
**Git SHA:** ac7d41b7fe7849025f6666bd602ac3f7726f8dc8
**Run ID:** <current_run_id>
**Decision:** HALT -- no market passes DATA-09 economics gate.

## Per-Market Evaluation

| market_id | R_apr_on_collateral | alt_yield_used | fill_loss_used | threshold | delta | halt_reason |
|-----------|---------------------|----------------|----------------|-----------|-------|-------------|
| MARKET-PASSING-DATA08 | 0.0600 | 0.0500 | 0.0200 | 0.0700 | -0.0100 | R_apr 0.0600 < threshold 0.0700 |

## Knobs Snapshot (RUN_MANIFEST config tree)

```json
{
  "mode": "paper",
  "strategy_version": "v0.5.0",
  "market_id": "TBD",
  "side": "long",
  "root_wallet_address": "0xaF3128a55fb3a1023369998B0f86490fF685e27B",
  "agent_wallet_address": "0xcaeC51f15AD46466C95e463C89c4782bEEC7c8A4",
  "strategy": {
    "voluntary_cancel_forfeits_accumulated": false,
    "target_share": 0.05
  },
  "execution": {
    "cancel_latency_budget_s": 5.0,
    "require_success_default": true,
    "agent_wallet_gas_warn_multiples": 50,
    "agent_wallet_gas_halt_multiples": 20,
    "agent_wallet_gas_emergency_multiples": 5
  },
  "data": {
    "markets_poll_interval_s": 30.0,
    "e_liq_poll_interval_s": 5.0,
    "chain_time_cache_ttl_s": 1.0,
    "rpc_url_arbitrum": "https://arb1.arbitrum.io/rpc",
    "boros_rest_base": "https://api.boros.finance/open-api/v1"
  },
  "infra": {
    "sqlite_path": "state/state.sqlite",
    "logs_dir": "logs",
    "zmq_cmd_endpoint": "ipc:///tmp/boros.cmd",
    "zmq_events_brain_endpoint": "ipc:///tmp/boros.events.brain",
    "zmq_events_hands_endpoint": "ipc:///tmp/boros.events.hands",
    "zmq_kill_endpoint": "ipc:///tmp/boros.cmd.kill",
    "heartbeat_interval_s": 5.0,
    "heartbeat_timeout_misses": 3,
    "chain_drift_warn_s": 5.0,
    "chain_drift_halt_s": 30.0
  },
  "screener": {
    "min_time_to_maturity_days": 30,
    "trades_window_days": 60,
    "realized_vol_window_days": 14,
    "reversal_count_window_days": 3,
    "alt_yield": 0.05,
    "fill_loss_coarse_bound": 0.02
  },
  "fill_model": {
    "window_days": 14,
    "bin_duration_s": 60.0,
    "refit_cadence_s": 900.0,
    "covariate_whitelist": [
      "basis_spread",
      "imbalance",
      "sin_settlement",
      "cos_settlement",
      "ewma_vol"
    ],
    "queue_tracker_bias_mode": "pessimistic",
    "gof_ks_pval_threshold": 0.0,
    "gof_lr_ratio_threshold": null,
    "fit_warn_staleness_s": 1800.0,
    "fit_max_staleness_s": 3600.0,
    "bracket_width_warn_multiplier": 0.5,
    "min_events_per_param_ratio": 10
  },
  "markets": []
}
```

## Halt Semantics

- `drop(market) iff R_apr_on_collateral < alt_yield + fill_loss_coarse_bound` -> threshold = 0.0700
- delta < 0 for EVERY shortlist candidate -> shortlist empty -> project halts.
- No downstream phase (2+) work is started until a market passes.

## Possible Remediations

1. Wait for new markets (DATA-10 daily re-screen will detect new-entrants; this report reruns).
2. Re-verify `alt_yield` against current Arbitrum stablecoin market (may have shifted).
3. Re-verify `fill_loss_coarse_bound` against current CLO-edge fill rates (A1 -- Phase 3 refines).
4. Escalate to PROJECT.md review: is the thesis still viable?

Filed to wiki: [[Economics kill-switch v0.5]]
