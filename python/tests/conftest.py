"""Shared pytest fixtures for the boros_brain test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.loader import load_config
from boros_brain.config.schema import BotConfig

# repo root (python/tests → python/ → repo root)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def default_yaml_path() -> Path:
    return ROOT / "strategy" / "v0.5-default.yaml"


@pytest.fixture
def default_config(default_yaml_path: Path) -> BotConfig:
    """strategy/v0.5-default.yaml uses placeholder wallet strings (TBD).

    Those satisfy the `str` type — Phase 8 will add a live-mode pre-deploy
    validator that rejects placeholder values when `mode == 'live'`.
    """
    return load_config(default_yaml_path)


@pytest.fixture
def tmp_sqlite_path(tmp_path: Path) -> Path:
    """Isolated SQLite DB per test. Used once plan 01-02 lands DB code."""
    return tmp_path / "test_state.sqlite"


@pytest.fixture
def frozen_chain_time() -> int:
    """Deterministic chain timestamp for tests. Used once INFRA-14 code lands."""
    return 1714089600  # 2026-04-26T00:00:00Z
