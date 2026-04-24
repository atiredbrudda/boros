"""Single writer for the `run_manifests` table (brain-owned) — INFRA-06.

PROTO-02 single-writer discipline. The RUN_MANIFEST emitter writes here once at
boot (and once per mid-run knob change, with `parent_run_id` pointing at the
previous run_id — FK enforced).

`config_json` is serialized from `BotConfig.model_dump(mode='json')` via
`json.dumps`. The caller is responsible for producing the JSON string; the
writer does not validate the payload shape.
"""

from __future__ import annotations

import sqlite3


def insert_run_manifest(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    parent_run_id: str | None,
    started_at_iso: str,
    mode: str,
    strategy_version: str,
    git_sha: str,
    git_dirty: int,
    market_id: str,
    side: str,
    wallet_address_hash: str,
    config_json: str,
) -> None:
    conn.execute(
        "INSERT INTO run_manifests "
        "(run_id, parent_run_id, started_at_iso, mode, strategy_version, git_sha, "
        "git_dirty, market_id, side, wallet_address_hash, config_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            parent_run_id,
            started_at_iso,
            mode,
            strategy_version,
            git_sha,
            git_dirty,
            market_id,
            side,
            wallet_address_hash,
            config_json,
        ),
    )
