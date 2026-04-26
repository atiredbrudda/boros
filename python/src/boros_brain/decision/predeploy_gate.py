"""A5 absorbed — pre-deployment re-screen gate (Plan 04-06).

Before going live, the operator runs:
    python -m boros_brain.decision predeploy-gate --config strategy/v0.5-default.yaml

This re-runs the economics gate against the current screener metrics to confirm
the configured market is still in the shortlist. If the market has been screened
out since the last calibration, the gate fails and the bot must not be deployed.

Pitfall #8: git_sha + config_hash are stamped into state.predeploy_gate_records so
Phase 7 live boot can refuse to start if the code or config has changed since the
last successful gate run.

[[predeploy-gate-cli]]: CLI usage, Pitfall #8, Phase 7 boot guard
[[economics-kill-switch-v05]]: underlying economics screener gate
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..screener import economics_gate as _economics_gate_mod
from ..state.db import open_connection
from ..state.writers.predeploy_gate_records import insert_predeploy_gate_record

log = structlog.get_logger(__name__)

__all__ = ["run_predeploy_gate"]


def _read_git_sha() -> tuple[str, bool]:
    """Return (git_sha, git_dirty) for the current HEAD commit.

    Falls back to ("unknown", True) on any subprocess error (e.g., not in a git
    repo or git not installed). Pitfall #8: this data is stamped in every gate
    record for Phase 7 boot provenance checks.
    """
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty_output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(dirty_output)
        return sha, dirty
    except Exception:  # noqa: BLE001
        return "unknown", True


def run_predeploy_gate(
    config: BotConfig,
    *,
    sqlite_path: Path,
    run_id: str,
    wiki_dir: Path | None = None,
) -> int:
    """A5 absorbed — re-run economics gate; write predeploy_gate_records row + wiki page.

    Parameters
    ----------
    config:
        Live BotConfig — defines the configured market and screener knobs.
    sqlite_path:
        Path to the SQLite WAL state DB. The predeploy_gate_records row is
        persisted here for Phase 7 boot guard reads.
    run_id:
        Active run_id for traceability in the gate record.
    wiki_dir:
        Override wiki output directory (default: LLM Wiki boros workspace).
        Inject a tmp path in tests to avoid polluting the real wiki.

    Returns
    -------
    int
        0 if the gate passes (configured market is in the shortlist).
        1 if the gate fails (market screened out) or on screener error.
    """
    # 1. Re-run economics gate to get current shortlist.
    # Use module-level access so tests can patch boros_brain.screener.economics_gate.run_screener.
    try:
        shortlist: list[str] = _economics_gate_mod.run_screener(config)
    except Exception as exc:  # noqa: BLE001
        log.error("predeploy_gate.screener_failed", err=str(exc))
        return 1

    # 2. Verify the configured market is in the shortlist.
    configured_market: str | None = config.markets[0].market_id if config.markets else None
    gate_passed = bool(configured_market and configured_market in shortlist)

    log.info(
        "predeploy_gate.result",
        gate_passed=gate_passed,
        configured_market=configured_market,
        shortlist=shortlist,
    )

    # 3. Compute git_sha + git_dirty + config_hash for Pitfall #8 provenance.
    git_sha, git_dirty = _read_git_sha()
    config_json = config.model_dump_json()
    config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:16]

    # 4. Write wiki page (separate from DB to maintain the wiki audit trail).
    _wiki_dir = wiki_dir or Path("/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki")
    _write_wiki_page(
        wiki_dir=_wiki_dir,
        gate_passed=gate_passed,
        configured_market=configured_market,
        shortlist=shortlist,
        git_sha=git_sha,
        git_dirty=git_dirty,
        config_hash=config_hash,
        run_id=run_id,
    )

    # 5. Persist gate record to state.predeploy_gate_records.
    chain_ts = int(datetime.now(UTC).timestamp())
    wiki_page_path = str(_wiki_dir / f"predeploy-gate-pass-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.md")
    with open_connection(sqlite_path) as conn:
        insert_predeploy_gate_record(
            conn,
            gate_passed=gate_passed,
            git_sha=git_sha,
            git_dirty=git_dirty,
            config_hash=config_hash,
            wiki_page_path=wiki_page_path,
            run_id=run_id,
            chain_ts=chain_ts,
        )
        conn.commit()

    return 0 if gate_passed else 1


def _write_wiki_page(
    *,
    wiki_dir: Path,
    gate_passed: bool,
    configured_market: str | None,
    shortlist: list[str],
    git_sha: str,
    git_dirty: bool,
    config_hash: str,
    run_id: str,
) -> None:
    """Write a time-stamped wiki page recording the gate result for audit trail.

    Uses a subdirectory-safe filename. Silently skips if the wiki_dir doesn't
    exist and can't be created (e.g. tests with non-existent tmp paths).
    """
    try:
        wiki_dir.mkdir(parents=True, exist_ok=True)
        filename = f"predeploy-gate-result-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.md"
        page = wiki_dir / filename
        result_str = "PASS" if gate_passed else "FAIL"
        page.write_text(
            f"---\n"
            f"title: Pre-deployment Gate Result\n"
            f"status: Current — pre-deployment validation\n"
            f"phase: 4\n"
            f"plan: 04-06\n"
            f"date: {datetime.now(UTC).isoformat()}\n"
            f"---\n\n"
            f"# Pre-deployment Gate\n\n"
            f"**Status:** Current — pre-deployment validation\n"
            f"**Result:** {result_str}\n"
            f"**Configured market:** {configured_market}\n"
            f"**Shortlist:** {shortlist}\n"
            f"**git_sha:** {git_sha}\n"
            f"**git_dirty:** {git_dirty}\n"
            f"**config_hash:** {config_hash}\n"
            f"**run_id:** {run_id}\n\n"
            f"[[predeploy-gate-cli]]\n"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("predeploy_gate.wiki_write_failed", err=str(exc))
