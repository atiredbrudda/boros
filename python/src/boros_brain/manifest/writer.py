"""RUN_MANIFEST writer (INFRA-06, PROTO-01).

The manifest is built by reflecting over `BotConfig.model_dump(mode='json')`.
Adding a knob to `BotConfig` without updating this file is impossible — the
reflection walks every nested StrictBase recursively. PITFALLS §D2 + T-03-01.

`write_manifest` is the atomic boot step: writes sidecar JSON AND inserts the
`run_manifests` SQLite row in a single `open_connection()` context. Callers
configure structlog AFTER this returns so the first log line is the RUN_MANIFEST
record itself.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from ..config.schema import BotConfig
from ..state.db import open_connection
from ..state.writers.run_manifests import insert_run_manifest
from .schema import RunManifest


def _git_sha() -> str:
    """Return current HEAD SHA, or 40 zeros if git is unavailable."""
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return sha or "0" * 40
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "0" * 40


def _git_dirty() -> bool:
    """True iff the working tree has uncommitted changes vs. HEAD."""
    try:
        # git diff --quiet exits 0 on clean, 1 on dirty, >1 on error.
        return (
            subprocess.call(
                ["git", "diff", "--quiet", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            == 1
        )
    except FileNotFoundError:
        return False


def _wallet_address_hash(addr: str) -> str:
    """sha256(lower(addr))[:16] — deterministic, not reversible, fits a log line."""
    return hashlib.sha256(addr.lower().encode()).hexdigest()[:16]


def build_run_manifest(config: BotConfig, parent_run_id: str | None = None) -> RunManifest:
    """Reflect over BotConfig and return an immutable RunManifest."""
    return RunManifest(
        run_id=str(ULID()),
        parent_run_id=parent_run_id,
        started_at=datetime.now(UTC).isoformat(),
        mode=config.mode,
        strategy_version=config.strategy_version,
        git_sha=_git_sha(),
        git_dirty=_git_dirty(),
        market_id=config.market_id,
        side=config.side,
        wallet_address_hash=_wallet_address_hash(config.root_wallet_address),
        # model_dump(mode='json') walks every nested StrictBase recursively.
        # This is the reflection that makes PITFALLS §D2 mechanically unskippable.
        config=config.model_dump(mode="json"),
        chain_time_drift_at_start_seconds=None,
        agent_wallet_gas_balance_at_start=None,
    )


def write_manifest(
    manifest: RunManifest,
    *,
    logs_dir: Path | str,
    sqlite_path: Path | str,
) -> Path:
    """Emit sidecar JSON AND insert into the `run_manifests` SQLite table.

    Returns the sidecar path so callers (tests, entry points) can round-trip it.
    Parent directories are created as needed; the `run_manifests` table must
    already exist (Alembic `upgrade head` runs on first brain boot before this).
    """
    logs_dir = Path(logs_dir)
    sqlite_path = Path(sqlite_path)

    date_dir = logs_dir / datetime.now(UTC).strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = date_dir / f"{manifest.run_id}.manifest.json"
    sidecar_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))

    with open_connection(sqlite_path) as conn:
        insert_run_manifest(
            conn,
            run_id=manifest.run_id,
            parent_run_id=manifest.parent_run_id,
            started_at_iso=manifest.started_at,
            mode=manifest.mode,
            strategy_version=manifest.strategy_version,
            git_sha=manifest.git_sha,
            git_dirty=1 if manifest.git_dirty else 0,
            market_id=manifest.market_id,
            side=manifest.side,
            wallet_address_hash=manifest.wallet_address_hash,
            config_json=json.dumps(manifest.config),
        )
        # open_connection uses isolation_level=None (autocommit) so the INSERT is
        # already durable; explicit commit is a no-op but kept for symmetry with
        # other writers that use explicit BEGIN/COMMIT blocks.
        conn.commit()

    return sidecar_path
