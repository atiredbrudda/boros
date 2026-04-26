"""Backtest sweeps — cancel-latency (BACK-03), competition (BACK-04),
forfeit_branch (BACK-06), perturbation (BACK-08).

Each sweep emits one BacktestRunOutput row per grid value, plus a derived
finite-difference curve (dP&L/dL or dP&L/dQ_competing) for monotonicity diagnostics.

[[backtest-cancel-latency-sweep]]
[[backtest-competition-sweep]]
"""

__all__: list[str] = []
