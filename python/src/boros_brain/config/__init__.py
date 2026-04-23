"""Pydantic v2 BotConfig — single source of truth for every knob (PROTO-04)."""

from .loader import load_config
from .schema import (
    BotConfig,
    DataConfig,
    ExecutionConfig,
    InfraConfig,
    MarketCalibration,
    ScreenerConfig,
    StrategyConfig,
    StrictBase,
)

__all__ = [
    "BotConfig",
    "DataConfig",
    "ExecutionConfig",
    "InfraConfig",
    "MarketCalibration",
    "ScreenerConfig",
    "StrategyConfig",
    "StrictBase",
    "load_config",
]
