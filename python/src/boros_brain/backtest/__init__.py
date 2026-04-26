"""Backtest package — event-driven queue-aware replay engine (Phase 5).

Sub-modules (in dependency order):
  backtest.schemas          — BacktestRunOutput / ShipGateVerdict / ThresholdComponents / SweepResult
  backtest.config           — BacktestConfig Pydantic sub-model (PROTO-04 SSoT)
  backtest.synthetic_orders — SyntheticOrder dataclass + SyntheticOrderLedger
  backtest.cancel_latency   — ScheduledClose + LatencyScheduler (two-axis compound)
  backtest.replay           — ReplayEngine: eventIndex-ordered loop, AMM conservation, look-ahead guards
  backtest.bootstrap        — seed_from_manifest + block_bootstrap_pnl (deterministic via manifest)
  backtest.ship_gate        — ShipGateHalt + assemble_threshold + evaluate_ship_gate + write_ship_gate_report
  backtest.report           — Hive-partitioned parquet writer + plot generators
  backtest.sweeps.*         — cancel_latency sweep, competition sweep, forfeit_branch, perturbation grid
  backtest.cli              — argparse entry-point (run + plot subcommands)

All source modules are stubbed until their implementing Wave lands. The only
Plan-05-01 artifact here is backtest.config (BacktestConfig PROTO-04 SSoT) —
all other sub-modules land in Waves 1-3.

[[backtest-replay-engine-v05]]: queue-aware AMM-aware replay design + eventIndex ordering
[[backtest-bootstrap-methodology-v05]]: block bootstrap seed-from-manifest determinism
"""

__all__: list[str] = []
