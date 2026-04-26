"""BACK-03 — dP&L/dL sign: central-finite-difference is everywhere negative.

Test functions:
  - test_dpnl_dl_negative_on_synthetic_always_fills_scenario: central-finite-difference is everywhere negative

[[backtest-cancel-latency-sweep]]
[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

from boros_brain.backtest.schemas import BacktestRunOutput
from boros_brain.backtest.sweeps.cancel_latency import compute_dpnl_dl

# Deterministic "always-fills" P&L: pnl = -L * 0.01 → dP&L/dL = -0.01 everywhere.
_ALWAYS_FILLS_GRID = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


def _make_row(L: float, git_sha: str = "abc1234") -> BacktestRunOutput:
    """Minimal BacktestRunOutput with synthetic always-fills P&L = -L * 0.01."""
    return BacktestRunOutput(
        run_id=f"test-{L}",
        parent_run_id="parent-001",
        git_sha=git_sha,
        strategy_version="0.5.0",
        market_id="BINANCE-ETHUSDT-29MAY2026",
        side="long",
        sweep_axis="cancel_latency",
        sweep_value=float(L),
        raw_pnl_pendle=float(-L * 0.01),
        raw_pnl_usd=float(-L * 0.01),
        annualized_pnl_pct=float(-L * 0.01),
        sharpe_equivalent=0.0,
        max_drawdown_pct=0.0,
        n_decisions=10,
        n_fills=10,
        n_cancels=0,
        n_purges=0,
        cumulative_fees_pendle=0.0,
        cumulative_gas_pendle=0.0,
        predicted_p_fill_mean=1.0,
        realized_fill_rate=1.0,
        calibration_residual=0.0,
        e_liq_calibrated_at="2026-01-01T00:00:00Z",
        event_index_coverage="full",
        voluntary_cancel_branch="benign",
        parquet_partition=f"run_id=test-{L}/sweep_axis=cancel_latency",
    )


def test_dpnl_dl_negative_on_synthetic_always_fills_scenario() -> None:
    """BACK-03: dP&L/dL < 0 everywhere in an always-fills synthetic scenario.

    When every order fills (worst case), increasing cancel latency L always
    worsens P&L. The central-finite-difference dP&L/dL must be negative at
    every grid point.

    Deterministic fixture: pnl(L) = -L * 0.01 → exact slope = -0.01 everywhere.
    """
    rows = [_make_row(L) for L in _ALWAYS_FILLS_GRID]
    slopes = compute_dpnl_dl(rows)

    assert len(slopes) == len(_ALWAYS_FILLS_GRID), f"Expected {len(_ALWAYS_FILLS_GRID)} slope values, got {len(slopes)}"

    for L_i, slope in slopes:
        assert slope < 0, f"Expected dP&L/dL < 0 at L={L_i}, got slope={slope}"
        # For the linear function pnl = -L*0.01, all differences are exactly -0.01
        assert abs(slope - (-0.01)) < 1e-9, f"Expected slope ≈ -0.01 at L={L_i}, got {slope}"
