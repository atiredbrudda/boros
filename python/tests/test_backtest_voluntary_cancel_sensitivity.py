"""BACK-06 — Voluntary-cancel sensitivity sweep.

[[backtest-voluntary-cancel-sensitivity-row]]
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.backtest.schemas import BacktestRunOutput, ReplayConfig, ReplayOutput
from boros_brain.backtest.sweeps.forfeit_branch import run_forfeit_branch_sweep
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _build_synth_row(branch: str, pnl: float, run_id: str = "test-run") -> BacktestRunOutput:
    return BacktestRunOutput(
        run_id=run_id,
        git_sha="x",
        strategy_version="0.5",
        market_id=MARKET_ID,
        side="long",
        sweep_axis="base",
        sweep_value=0.0,
        raw_pnl_pendle=0.0,
        raw_pnl_usd=0.0,
        annualized_pnl_pct=pnl,
        sharpe_equivalent=0.0,
        max_drawdown_pct=0.0,
        n_decisions=0,
        n_fills=0,
        n_cancels=0,
        n_purges=0,
        cumulative_fees_pendle=0.0,
        cumulative_gas_pendle=0.0,
        predicted_p_fill_mean=0.05,
        realized_fill_rate=0.05,
        calibration_residual=0.0,
        e_liq_calibrated_at="2026-04-25T00:00:00Z",
        event_index_coverage="full",
        voluntary_cancel_branch=branch,  # type: ignore[arg-type]
        parquet_partition=f"run_id={run_id}/sweep_axis=base",
    )


@pytest.mark.asyncio
async def test_two_branches_produced(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sweep emits exactly 2 rows (benign + punitive)."""
    from boros_brain.backtest import replay as replay_mod

    call_count = {"n": 0}

    async def fake_run(self, **kwargs):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        branch = self.voluntary_cancel_branch
        return ReplayOutput(rows=[_build_synth_row(branch, 0.05)])

    monkeypatch.setattr(replay_mod.ReplayEngine, "run", fake_run)

    base_run = ReplayConfig(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path,
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=2.0,
    )
    parent_manifest = build_run_manifest(default_config)
    rows = await run_forfeit_branch_sweep(base_run, parent_manifest=parent_manifest, config=default_config)
    assert len(rows) == 2
    branches = {r.voluntary_cancel_branch for r in rows}
    assert branches == {"benign", "punitive"}
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_divergence_under_threshold_logs_sanity_pass(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Divergence < 10% -> sanity_check_pass; no forfeit_branch_load_bearing."""

    from boros_brain.backtest import replay as replay_mod

    pnl_per_branch = {"benign": 0.05, "punitive": 0.06}  # divergence = 0.01

    async def fake_run(self, **kwargs):  # type: ignore[no-untyped-def]
        b = self.voluntary_cancel_branch
        return ReplayOutput(rows=[_build_synth_row(b, pnl_per_branch[b])])

    monkeypatch.setattr(replay_mod.ReplayEngine, "run", fake_run)

    base_run = ReplayConfig(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path,
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=2.0,
    )
    parent_manifest = build_run_manifest(default_config)

    import structlog.testing

    with structlog.testing.capture_logs() as cap_logs:
        await run_forfeit_branch_sweep(base_run, parent_manifest=parent_manifest, config=default_config)

    events = [e.get("event", "") for e in cap_logs]
    pass_records = [e for e in events if "sanity_check_pass" in e]
    fail_records = [e for e in events if "forfeit_branch_load_bearing" in e]
    assert pass_records, f"no sanity_check_pass log; events: {events}"
    assert not fail_records, f"unexpected load_bearing log; events: {events}"


@pytest.mark.asyncio
async def test_divergence_over_threshold_emits_followup_flag(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Divergence >= 10% -> forfeit_branch_load_bearing flag (does NOT auto-fail ship-gate)."""
    from boros_brain.backtest import replay as replay_mod

    pnl_per_branch = {"benign": 0.05, "punitive": -0.10}  # divergence = 0.15

    async def fake_run(self, **kwargs):  # type: ignore[no-untyped-def]
        b = self.voluntary_cancel_branch
        return ReplayOutput(rows=[_build_synth_row(b, pnl_per_branch[b])])

    monkeypatch.setattr(replay_mod.ReplayEngine, "run", fake_run)

    base_run = ReplayConfig(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path,
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=2.0,
    )
    parent_manifest = build_run_manifest(default_config)

    import structlog.testing

    with structlog.testing.capture_logs() as cap_logs:
        await run_forfeit_branch_sweep(base_run, parent_manifest=parent_manifest, config=default_config)

    events_full = cap_logs  # list of dicts
    fail_records = [e for e in events_full if "forfeit_branch_load_bearing" in e.get("event", "")]
    assert fail_records, f"no forfeit_branch_load_bearing log; events: {[e.get('event') for e in events_full]}"
    assert abs(fail_records[0].get("divergence", 0) - 0.15) < 1e-9
