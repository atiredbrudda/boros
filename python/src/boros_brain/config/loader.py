"""YAML → BotConfig loader with extra='forbid' enforcement."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schema import BotConfig


def load_config(yaml_path: str | Path) -> BotConfig:
    """Load YAML file and validate against BotConfig.

    `extra='forbid'` means unknown keys raise ValidationError loudly — no silent
    drift between code and config (PROTO-04).
    """
    raw = yaml.safe_load(Path(yaml_path).read_text())
    return BotConfig.model_validate(raw)
