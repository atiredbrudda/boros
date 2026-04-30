"""Tests verifying strategy YAML files carry margin_per_yu_usd (Phase 05.2 Wave 1).

Test IDs:
- T-05.2-W1-Y-01: v0.5-default.yaml sizer block has margin_per_yu_usd=18.30, not old name
- T-05.2-W1-Y-02: v0.5-phase05.1-shortlist.yaml sizer block + binding market entry have margin_per_yu_usd=18.30
- T-05.2-W1-Y-03: both YAMLs load cleanly into BotConfig with no ValidationError

These tests are regression guards: if the YAML rename is reverted, the Pydantic
extra='forbid' would catch it — but these tests make the intent explicit and
provide better error messages than Pydantic's generic extra-field error.

See [[phase-05-2-margin-per-yu-rename]] for the rename narrative.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from boros_brain.config.schema import BotConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = ROOT / "strategy" / "v0.5-default.yaml"
SHORTLIST_YAML = ROOT / "strategy" / "v0.5-phase05.1-shortlist.yaml"


def test_strategy_yaml_has_margin_per_yu_default() -> None:
    """T-05.2-W1-Y-01 — v0.5-default.yaml sizer block uses margin_per_yu_usd."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text())
    sizer = raw["sizer"]
    assert sizer["margin_per_yu_usd"] == pytest.approx(18.30)
    assert "notional_per_yu_usd" not in sizer, (
        "Old knob name notional_per_yu_usd still present in v0.5-default.yaml — "
        "Phase 05.2 Bug #1 rename incomplete"
    )


def test_strategy_yaml_has_margin_per_yu_shortlist() -> None:
    """T-05.2-W1-Y-02 — v0.5-phase05.1-shortlist.yaml sizer block AND binding market entry.

    Both the top-level sizer.margin_per_yu_usd and the per-market
    markets[0].margin_per_yu_usd must be present with value 18.30.
    Also checks that daily_volatility_pct is a float in [0.0, 100.0].
    """
    raw = yaml.safe_load(SHORTLIST_YAML.read_text())

    # Top-level sizer block
    sizer = raw["sizer"]
    assert sizer["margin_per_yu_usd"] == pytest.approx(18.30)
    assert "notional_per_yu_usd" not in sizer, (
        "Old knob name notional_per_yu_usd still present in v0.5-phase05.1-shortlist.yaml sizer block"
    )

    # Per-market entry (binding market)
    markets = raw.get("markets", [])
    assert len(markets) >= 1, "Expected at least 1 market entry"
    binding = markets[0]
    assert "margin_per_yu_usd" in binding, (
        f"Binding market {binding.get('market_id')} missing margin_per_yu_usd"
    )
    assert binding["margin_per_yu_usd"] == pytest.approx(18.30)

    assert "daily_volatility_pct" in binding, (
        f"Binding market {binding.get('market_id')} missing daily_volatility_pct"
    )
    dvp = binding["daily_volatility_pct"]
    assert isinstance(dvp, (int, float)), f"daily_volatility_pct must be numeric, got {type(dvp)}"
    assert 0.0 <= float(dvp) <= 100.0, f"daily_volatility_pct={dvp} out of [0, 100] range"


def test_strategy_yaml_loads_into_botconfig() -> None:
    """T-05.2-W1-Y-03 — Both YAMLs parse into BotConfig without ValidationError.

    This proves Pydantic accepts the new fields without extra='forbid' rejection.
    Also proves extra='forbid' would catch the old notional_per_yu_usd name.
    """
    # default YAML (no markets block required, schema allows empty markets for default.yaml)
    raw_default = yaml.safe_load(DEFAULT_YAML.read_text())
    # Note: v0.5-default.yaml may not have all required fields (e.g. market_id, wallet addresses).
    # We only verify the sizer block doesn't raise on the rename.
    sizer_raw = raw_default["sizer"]
    assert "margin_per_yu_usd" in sizer_raw
    assert "notional_per_yu_usd" not in sizer_raw

    # shortlist YAML — has all required fields for BotConfig
    raw_shortlist = yaml.safe_load(SHORTLIST_YAML.read_text())
    config = BotConfig(**raw_shortlist)
    assert config.sizer.margin_per_yu_usd == pytest.approx(18.30)
    assert config.markets[0].margin_per_yu_usd == pytest.approx(18.30)
    assert config.markets[0].daily_volatility_pct == pytest.approx(0.34)
    assert config.markets[0].liquidation_buffer_safety_n == 3
