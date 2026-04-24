"""YAML -> BotConfig loader with extra='forbid' enforcement."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schema import BotConfig


def load_config(yaml_path: str | Path) -> BotConfig:
    """Load YAML file and validate against BotConfig.

    `extra='forbid'` means unknown YAML keys raise ValidationError loudly -- no silent
    drift between code and config (PROTO-04).
    """
    raw = yaml.safe_load(Path(yaml_path).read_text())
    return BotConfig.model_validate(raw)


def load_raw_yaml(yaml_path: str | Path) -> dict[str, object]:
    """Load YAML file and return the raw dict WITHOUT Pydantic validation.

    Used by economics_gate.py to assert that both `alt_yield` and
    `fill_loss_coarse_bound` are present as EXPLICIT keys in the operator-authored
    YAML BEFORE Pydantic applies defaults (T-01-12-01 -- no silent kill-switch bypass).
    """
    return yaml.safe_load(Path(yaml_path).read_text()) or {}
