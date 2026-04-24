"""DATA-10 daily re-screen scheduler.

Addresses PITFALLS §A5 (Competition crowding in during engineering window):
DATA-10 runs under launchd CalendarInterval while Phase 2+ are building the models,
so shortlist shifts are caught within 24h. If a market passed the economics gate
yesterday but fails today, or a new market has entered the candidate pool, the
operator knows within one daily cycle rather than discovering it weeks later.

Pipeline: ingest NDJSON deltas -> run screener (DATA-08) -> run economics gate
(DATA-09) -> diff today's shortlist vs yesterday's -> write rescreen_diff.json.

[[Daily re-screen scheduler]]
[[Economics kill-switch v0.5]]
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from .cli import run_screener
from .economics_gate import ConfigError, ProjectHalt, run_economics_gate

log = structlog.get_logger(__name__)

_YESTERDAY_SHORTLIST_PATH = Path("var/reports/shortlist_previous.json")


def _load_yesterday_shortlist() -> set[str]:
    """Load yesterday's shortlist from var/reports/shortlist_previous.json."""
    if _YESTERDAY_SHORTLIST_PATH.exists():
        return set(json.loads(_YESTERDAY_SHORTLIST_PATH.read_text()).get("markets", []))
    return set()


def _run_ingest_stage(config_path: str) -> None:
    """Stage 1: ingest any new NDJSON files from data/raw/ into parquet.

    Uses the data ingester CLI to process pending files. No-ops if no new files.
    """
    import subprocess

    # Run the ingester CLI for each known data kind.
    # In the v0.5 architecture, the operator drops NDJSON into data/raw/ manually;
    # the ingester picks up unprocessed files. We call it as a subprocess so the
    # ingester's own RUN_MANIFEST chain is preserved (parent_run_id linkage).
    kinds = ["market_trades", "order_book_raw", "order_book_combined", "underlying_apr", "settlement_md"]
    for kind in kinds:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "boros_brain.data.ingester",
                "--kind",
                kind,
                "--src",
                "data/raw/",
                "--dest",
                "data/parquet/",
                "--config",
                config_path,
            ],
            capture_output=True,
        )
        if result.returncode not in (0, 1):  # 0=ok, 1=no files (acceptable)
            log.warning(
                "rescreen.ingest_stage.nonzero",
                kind=kind,
                returncode=result.returncode,
            )
    log.info("rescreen.stage.ingest.done")


def _run_screener_stage(config_path: str) -> None:
    """Stage 2: run the DATA-08 screener, writing var/reports/screener_metrics.json."""
    from ..config.loader import load_config

    config = load_config(config_path)
    run_screener(config)
    log.info("rescreen.stage.screener.done")


def _run_gate_stage(config_path: str) -> list[str]:
    """Stage 3: run the DATA-09 economics gate, returning today's shortlist."""
    shortlist = run_economics_gate(config_path)
    log.info("rescreen.stage.gate.done", shortlist=shortlist)
    return shortlist


def _write_rescreen_diff(yesterday: set[str], today: set[str]) -> None:
    """Compute new-entrant / dropped / unchanged diff and write rescreen_diff.json.

    Emits structured WARNING log for each dropped market (operator alert).
    Emits INFO log for each new-entrant market.
    """
    new_entrants = sorted(today - yesterday)
    dropped = sorted(yesterday - today)
    unchanged = sorted(today & yesterday)

    for market_id in dropped:
        log.warning("rescreen.market_dropped", market_id=market_id)
    for market_id in new_entrants:
        log.info("rescreen.market_entered", market_id=market_id)

    diff = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "yesterday_shortlist": sorted(yesterday),
        "today_shortlist": sorted(today),
        "new_entrants": new_entrants,
        "dropped": dropped,
        "unchanged": unchanged,
    }
    Path("var/reports").mkdir(parents=True, exist_ok=True)
    Path("var/reports/rescreen_diff.json").write_text(json.dumps(diff, indent=2))


def run_daily_rescreen(config_path: str = "strategy/v0.5-default.yaml") -> int:
    """Run the full daily re-screen pipeline.

    Addresses PITFALLS §A5: Competition crowding in during engineering window.
    Running this daily under launchd CalendarInterval while Phase 2+ are being
    built ensures the shortlist never silently goes stale. Any market that was
    profitable yesterday but isn't today is flagged within 24h via rescreen_diff.json.

    Pipeline:
        1. Ingest any new NDJSON deltas from data/raw/ into parquet
        2. Run DATA-08 screener (writes var/reports/screener_metrics.json)
        3. Load yesterday's shortlist (var/reports/shortlist_previous.json)
        4. Run DATA-09 economics gate (returns today's shortlist)
        5. Diff today vs yesterday -> write var/reports/rescreen_diff.json
        6. Save today's shortlist as yesterday's for tomorrow's run

    Returns 0 on success. Raises ProjectHalt on empty shortlist (exit 1).
    Raises ConfigError on bad config (exit 2).
    """
    log.info("rescreen.start", config_path=config_path)

    # Stage 1: Ingest new NDJSON files
    log.info("rescreen.stage.ingest.start")
    _run_ingest_stage(config_path)

    # Stage 2: Run screener
    log.info("rescreen.stage.screener.start")
    _run_screener_stage(config_path)

    # Load yesterday's shortlist BEFORE running the gate (so diff is accurate even on halt)
    yesterday_shortlist = _load_yesterday_shortlist()

    # Stage 3: Run economics gate
    log.info("rescreen.stage.gate.start")
    try:
        today_list = _run_gate_stage(config_path)
        today_shortlist = set(today_list)
    except ProjectHalt:
        # Gate found empty shortlist: write diff (shows what was lost) then propagate
        today_shortlist = set()
        _write_rescreen_diff(yesterday_shortlist, today_shortlist)
        raise  # propagate exit code 1
    except ConfigError:
        raise  # propagate exit code 2

    # Stage 4: Diff and persist
    _write_rescreen_diff(yesterday_shortlist, today_shortlist)

    # Save today's shortlist for tomorrow's diff
    _YESTERDAY_SHORTLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _YESTERDAY_SHORTLIST_PATH.write_text(json.dumps({"markets": sorted(today_shortlist)}, indent=2))

    log.info("rescreen.done", shortlist=sorted(today_shortlist))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_daily_rescreen())
    except ProjectHalt:
        sys.exit(1)
    except ConfigError:
        sys.exit(2)
