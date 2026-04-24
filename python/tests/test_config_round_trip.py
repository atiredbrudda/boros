"""INFRA-02 / PROTO-04 — BotConfig round-trip, unknown-key, frozen-mutation tests.

Each test is one assertion. The suite is the only automated gate that prevents
knob-drift between code and the Pydantic schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig, DataConfig, StrategyConfig


def test_round_trip_yaml_to_config_to_yaml(default_yaml_path: Path, default_config: BotConfig, tmp_path: Path) -> None:
    """YAML → BotConfig → model_dump → YAML → BotConfig — two instances must be equal."""
    dumped = default_config.model_dump(mode="json")
    round_trip_path = tmp_path / "round_trip.yaml"
    round_trip_path.write_text(yaml.safe_dump(dumped, sort_keys=False))
    reloaded = load_config(round_trip_path)
    assert reloaded == default_config


def test_unknown_key_raises(default_config: BotConfig) -> None:
    """An unknown top-level key must be rejected by extra='forbid'."""
    payload = default_config.model_dump(mode="json")
    payload["unknown_key"] = "x"
    with pytest.raises(ValidationError):
        BotConfig.model_validate(payload)


def test_frozen_mutation_raises(default_config: BotConfig) -> None:
    """Mutation of a loaded BotConfig must raise (frozen=True)."""
    with pytest.raises((ValidationError, AttributeError, TypeError)):
        default_config.strategy.voluntary_cancel_forfeits_accumulated = True  # type: ignore[misc]


def test_voluntary_cancel_default_is_false() -> None:
    """D-01 / P0-01 lock — freshly constructed StrategyConfig defaults to False."""
    s = StrategyConfig()
    assert s.voluntary_cancel_forfeits_accumulated is False


def test_markets_list_max_length_one(default_config: BotConfig) -> None:
    """v0.5 single-market cap — two markets must be rejected."""
    m = {
        "market_id": "ETHUSDT-29MAY2026",
        "scale": 1.0,
        "s": 0.01,
        "clo_lower_thresh": 9300.0,
        "clo_upper_thresh": 9500.0,
        "fIndex_oracle_address": "0x0000000000000000000000000000000000000000",
        "maturity_ts": 1748505600,
    }
    payload = default_config.model_dump(mode="json")
    payload["markets"] = [m, {**m, "market_id": "BTCUSDT-26DEC2025"}]
    with pytest.raises(ValidationError):
        BotConfig.model_validate(payload)


def test_submission_path_not_in_schema() -> None:
    """P0-04 regression guard — [[Sign-only cancel primitive]].

    Send Txs Bot is the mandatory submission lane; direct-to-chain is ruled out.
    The `submission_path` knob was dropped from the schema. Re-adding it is a bug.
    """
    schema = BotConfig.model_json_schema()
    exec_props = schema["$defs"]["ExecutionConfig"]["properties"]
    assert "submission_path" not in exec_props, (
        "submission_path was dropped per P0-04 — [[Sign-only cancel primitive]]. "
        "Send Txs Bot is the mandatory submission lane; direct-to-chain is ruled out."
    )


def test_rpc_url_is_required() -> None:
    """DataConfig has no default for rpc_url_arbitrum — model_validate({}) must fail."""
    with pytest.raises(ValidationError):
        DataConfig.model_validate({})
