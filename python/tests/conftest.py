"""Shared pytest fixtures for the boros_brain test suite."""

from __future__ import annotations

import shutil
import tempfile
import uuid
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


@pytest.fixture
def ipc_dir() -> Path:
    """Short-path temp dir under /tmp so ZMQ ipc:// endpoints stay under the
    macOS 103-byte sockaddr_un.sun_path limit.

    pytest's `tmp_path` resolves to `/private/var/folders/.../pytest-of-…/pytest-N/…`
    which can easily exceed 103 chars and makes `zmq.PUB.bind('ipc://…')` fail
    with `ZMQError: ipc path is longer than 103 characters`.
    """
    base = Path(tempfile.gettempdir())
    # 8-char uuid suffix — keeps each fixture unique without exhausting sun_path.
    d = base / f"b_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
