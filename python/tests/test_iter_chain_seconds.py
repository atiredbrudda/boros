"""Phase 05.2 Wave 4 — _iter_chain_seconds helper unit tests.

Tests for the per-second event iterator that synthesises reward-accrual ticks
at 1 Hz on the chain-time clock between consecutive real trade events.

See [[backtest-1hz-tick-synthesis-2026-04-30]] for the full algorithm narrative.

Functions tested:
  - ReplayEngine._iter_chain_seconds
  - BacktestConfig.tick_period_s knob
  - BotConfig.backtest.tick_period_s appears in manifest leaf set
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from boros_brain.backtest.config import BacktestConfig
from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _make_engine(
    config: BotConfig,
    *,
    tick_period_s: float = 1.0,
) -> ReplayEngine:
    """Construct a minimal ReplayEngine for _iter_chain_seconds testing.

    Uses a modified config with the given tick_period_s.
    """
    modified_config = config.model_copy(
        update={
            "backtest": config.backtest.model_copy(
                update={"tick_period_s": tick_period_s}
            )
        }
    )
    manifest = build_run_manifest(modified_config)
    return ReplayEngine(
        config=modified_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=Path("/nonexistent"),
        sqlite_path=Path("/nonexistent"),
        cancel_latency_s=1.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )


def _make_event(ts: int, event_index: int = 0) -> dict[str, Any]:
    """Create a minimal trade-event dict with blockTimestamp and eventIndex."""
    return {
        "blockTimestamp": ts,
        "eventIndex": event_index,
        "rate": 0.01,
        "size_wei": 0,
        "market_id": MARKET_ID,
    }


def test_iter_chain_seconds_monotonic_count(default_config: BotConfig) -> None:
    """Given 2 real events at t=1700000000 and t=1700000010 (10s apart),
    iterator yields 11 tuples; chain_ts values are strictly monotonic ascending
    [1700000000..1700000010]; tuples at endpoints carry the real event dict;
    intermediate 9 tuples carry evt=None.
    """
    engine = _make_engine(default_config, tick_period_s=1.0)

    t0 = 1_700_000_000
    t1 = t0 + 10
    real_events = iter([_make_event(t0), _make_event(t1)])

    results = list(engine._iter_chain_seconds(real_events))

    # 11 tuples for t=0..10
    assert len(results) == 11, f"Expected 11 tuples, got {len(results)}"

    # chain_ts values are [t0, t0+1, ..., t1]
    chain_tses = [r[0] for r in results]
    assert chain_tses == list(range(t0, t1 + 1)), (
        f"Expected monotonic ascending chain_ts from {t0} to {t1}, got {chain_tses}"
    )

    # First and last tuples have the real events
    assert results[0][1] is not None, "First tuple should have real event"
    assert results[0][1]["blockTimestamp"] == t0
    assert results[-1][1] is not None, "Last tuple should have real event"
    assert results[-1][1]["blockTimestamp"] == t1

    # Intermediate tuples have evt=None
    for i in range(1, 10):
        assert results[i][1] is None, f"Intermediate tuple {i} should have evt=None"


def test_iter_chain_seconds_single_event(default_config: BotConfig) -> None:
    """One real event yields exactly one tuple."""
    engine = _make_engine(default_config, tick_period_s=1.0)

    t0 = 1_700_000_000
    real_events = iter([_make_event(t0)])

    results = list(engine._iter_chain_seconds(real_events))

    assert len(results) == 1, f"Expected 1 tuple, got {len(results)}"
    assert results[0][0] == t0
    assert results[0][1] is not None
    assert results[0][1]["blockTimestamp"] == t0


def test_iter_chain_seconds_empty(default_config: BotConfig) -> None:
    """Empty iterator yields zero tuples (no exception)."""
    engine = _make_engine(default_config, tick_period_s=1.0)

    results = list(engine._iter_chain_seconds(iter([])))

    assert results == [], f"Expected empty list, got {results}"


def test_iter_chain_seconds_handles_burst(default_config: BotConfig) -> None:
    """Two events at the same chain_ts (e.g. 1700000000 with eventIndex 0 and 1)
    yield the real events in eventIndex order without synthesised tick between them
    (since dt=0).
    """
    engine = _make_engine(default_config, tick_period_s=1.0)

    t0 = 1_700_000_000
    evt_a = _make_event(t0, event_index=0)
    evt_b = _make_event(t0, event_index=1)
    real_events = iter([evt_a, evt_b])

    results = list(engine._iter_chain_seconds(real_events))

    # Two events at same ts → two tuples, both real
    assert len(results) == 2, f"Expected 2 tuples for burst at same ts, got {len(results)}"
    assert results[0][0] == t0
    assert results[0][1] is evt_a
    assert results[1][0] == t0
    assert results[1][1] is evt_b


def test_iter_chain_seconds_respects_tick_period(default_config: BotConfig) -> None:
    """With tick_period_s=10.0 and events 100s apart, iterator yields 11 tuples
    (every 10th second: t0, t0+10, ..., t0+100).
    """
    engine = _make_engine(default_config, tick_period_s=10.0)

    t0 = 1_700_000_000
    t1 = t0 + 100
    real_events = iter([_make_event(t0), _make_event(t1)])

    results = list(engine._iter_chain_seconds(real_events))

    assert len(results) == 11, f"Expected 11 tuples (0..100 step 10), got {len(results)}"

    chain_tses = [r[0] for r in results]
    expected_tses = list(range(t0, t1 + 1, 10))
    assert chain_tses == expected_tses, (
        f"Expected chain_ts = {expected_tses}, got {chain_tses}"
    )

    # First and last carry real events
    assert results[0][1] is not None
    assert results[-1][1] is not None

    # Intermediate carry None
    for i in range(1, 10):
        assert results[i][1] is None, f"Intermediate tuple {i} should have evt=None"


def test_botconfig_has_tick_period_s_knob(default_config: BotConfig) -> None:
    """BotConfig.backtest.tick_period_s exists; default 1.0; ge=0.1; le=60.0;
    appears in manifest leaf set (PROTO-04 SSoT).
    """
    from pydantic import BaseModel

    def _collect_leaf_paths(
        model_cls: type[BaseModel], prefix: tuple[str, ...] = ()
    ) -> set[tuple[str, ...]]:
        leaves: set[tuple[str, ...]] = set()
        for name, info in model_cls.model_fields.items():
            ann = info.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                leaves |= _collect_leaf_paths(ann, prefix + (name,))
                continue
            origin = getattr(ann, "__origin__", None)
            args = getattr(ann, "__args__", ())
            if origin in (list, tuple) and args:
                inner = args[0]
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    leaves.add(prefix + (name,))
                    continue
            leaves.add(prefix + (name,))
        return leaves

    # 1. Knob present on BacktestConfig
    assert hasattr(BacktestConfig, "model_fields")
    assert "tick_period_s" in BacktestConfig.model_fields, (
        "BacktestConfig must have tick_period_s field"
    )

    # 2. Default value is 1.0
    cfg = BacktestConfig()
    assert cfg.tick_period_s == 1.0, f"Expected default tick_period_s=1.0, got {cfg.tick_period_s}"

    # 3. Validation constraints: ge=0.1 (rejects below), le=60.0 (rejects above)
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        BacktestConfig(tick_period_s=0.09)  # below ge=0.1

    with pytest.raises(pydantic.ValidationError):
        BacktestConfig(tick_period_s=60.1)  # above le=60.0

    # 4. Leaf appears in BotConfig manifest reflection
    leaves = _collect_leaf_paths(BotConfig)
    leaf_strs = [".".join(leaf) for leaf in leaves]
    assert "backtest.tick_period_s" in leaf_strs, (
        f"backtest.tick_period_s missing from BotConfig leaf paths. "
        f"Backtest leaves: {[s for s in leaf_strs if s.startswith('backtest.')]}"
    )

    # 5. Build a manifest and verify the knob round-trips
    manifest = build_run_manifest(default_config)
    config_tree = manifest.config
    assert "backtest" in config_tree, "manifest.config must contain 'backtest' key"
    assert "tick_period_s" in config_tree["backtest"], (
        f"tick_period_s missing from manifest config.backtest. "
        f"Keys: {list(config_tree['backtest'].keys())}"
    )
    assert config_tree["backtest"]["tick_period_s"] == 1.0
