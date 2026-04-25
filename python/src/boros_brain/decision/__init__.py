"""Decision engine package — EV-based cancel rule + predictive circuit breakers.

Sub-modules (in dependency order):
  decision.schemas          — EvaluateInput / EvaluateOutput Pydantic shapes
  decision.config           — DecisionEngineConfig + 10 BreakerConfig sub-models
  decision.breakers.base    — Breaker ABC + BreakerSignal
  decision.breakers.*       — 10 individual breakers (SAFE-01..09 + B5)
  decision.gas_history      — DECIDE-03 cancel_cost EWMA cache (Plan 04-03)
  decision.engine           — DECIDE-01/02 evaluate() compositor (Plan 04-03)
  decision.breaker_coordinator — SAFE-10 exclusive kill authority (Plan 04-06)
  decision.predeploy_gate   — A5 absorbed pre-deployment re-screen gate (Plan 04-06)
  decision.cli              — argparse entry-point (Plan 04-06)

The engine, gas_history, breaker_coordinator, predeploy_gate, and cli modules
are stubbed until plans 04-03 and 04-06 land them.

[[ev-cancel-rule]]: EV = R_share * P(no_fill) - E[loss|fill] * P(fill) - cancel_cost * P(purge)
[[circuit-breakers-v05]]: ten predictive breakers feeding BreakerCoordinator
"""

__all__: list[str] = []
