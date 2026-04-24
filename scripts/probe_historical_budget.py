#!/usr/bin/env python3
"""A6 spike — attempt historical reward-budget reconstruction from distributor events.

Per 01-RESEARCH.md Assumption A6: likely infeasible — this script attempts
reconstruction before falling back to forward-only logging.

Time-boxed per Planning Context: <= 1 day operator effort.

If infeasible: `reward_budget_history` remains forward-only from pipeline go-live.
Pre-pipeline backtest rows MUST use `data_source='synthetic_current'` (PITFALLS §B6).

Usage:
    python scripts/probe_historical_budget.py [--dry-run]

    --dry-run   Skip all RPC/network calls. Write a stub verdict JSON (for CI smoke tests).

Verdict written to: var/reports/a6_historical_budget_verdict.json

Fields:
    feasible: bool
    events_found: list[str]   event names that carry budget data
    sample_reconstructed: dict | None   (if feasible — 4 sample weekly rows)
    blockers: list[str]   what prevented reconstruction if not feasible
    time_spent_hours: float
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

OUT = Path("var/reports/a6_historical_budget_verdict.json")

# Candidate Boros distributor event names to probe for budget data.
# Per 01-RESEARCH.md Assumption A6: we do not know the ABI in advance.
# The spike enumerates these against the live contract.
_CANDIDATE_EVENT_NAMES = [
    "BudgetSet",
    "EmissionUpdated",
    "EpochBudgetPosted",
    "LiquidityBudgetSet",
    "RewardBudgetAllocated",
]


def _write_verdict(verdict: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(verdict, indent=2))
    print(f"Verdict written to {OUT}")
    print(json.dumps(verdict, indent=2))


def run_dry_run() -> int:
    """Dry-run mode: write a stub verdict without any RPC calls.

    Used by CI smoke tests and during development before RPC is configured.
    The stub verdict documents the expected output format and declares infeasible
    (the anticipated outcome per 01-RESEARCH.md Assumption A6) until proven otherwise.
    """
    verdict: dict = {
        "feasible": False,
        "events_found": [],
        "sample_reconstructed": None,
        "blockers": ["dry_run_mode"],
        "time_spent_hours": 0.0,
        "note": (
            "Dry-run mode — no RPC calls made. "
            "Run without --dry-run with RPC_URL_ARBITRUM set to perform the real spike. "
            "Per 01-RESEARCH.md Assumption A6: historical E_liq reconstruction is "
            "likely infeasible; if so, reward_budget_history remains forward-only and "
            "Phase-5 backtest rows from pre-pipeline data MUST use "
            "data_source='synthetic_current' (PITFALLS §B6)."
        ),
    }
    _write_verdict(verdict)
    return 0


def run_spike() -> int:
    """Live spike: attempt reconstruction from Boros distributor contract events.

    Prerequisites:
        RPC_URL_ARBITRUM   env var — Arbitrum JSON-RPC endpoint
        BOROS_DISTRIBUTOR_ADDRESS (optional) — distributor contract address
        configs/distributor_abi.json (optional) — ABI file (else fetches from Arbiscan)
    """
    start = time.time()

    rpc_url = os.environ.get("RPC_URL_ARBITRUM", "")
    if not rpc_url:
        verdict = {
            "feasible": False,
            "events_found": [],
            "sample_reconstructed": None,
            "blockers": ["RPC_URL_ARBITRUM_not_set"],
            "time_spent_hours": (time.time() - start) / 3600,
        }
        _write_verdict(verdict)
        return 1

    try:
        from web3 import Web3  # type: ignore[import-untyped]
    except ImportError:
        verdict = {
            "feasible": False,
            "events_found": [],
            "sample_reconstructed": None,
            "blockers": ["web3_not_installed"],
            "time_spent_hours": (time.time() - start) / 3600,
        }
        _write_verdict(verdict)
        return 1

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        verdict = {
            "feasible": False,
            "events_found": [],
            "sample_reconstructed": None,
            "blockers": ["rpc_unreachable"],
            "time_spent_hours": (time.time() - start) / 3600,
        }
        _write_verdict(verdict)
        return 1

    distributor_address = os.environ.get("BOROS_DISTRIBUTOR_ADDRESS", "")
    abi_path = Path("configs/distributor_abi.json")

    if not distributor_address:
        verdict = {
            "feasible": False,
            "events_found": [],
            "sample_reconstructed": None,
            "blockers": ["BOROS_DISTRIBUTOR_ADDRESS_not_set"],
            "time_spent_hours": (time.time() - start) / 3600,
        }
        _write_verdict(verdict)
        return 1

    if not abi_path.exists():
        verdict = {
            "feasible": False,
            "events_found": [],
            "sample_reconstructed": None,
            "blockers": ["abi_not_available — provide configs/distributor_abi.json"],
            "time_spent_hours": (time.time() - start) / 3600,
        }
        _write_verdict(verdict)
        return 1

    # Load ABI and scan for budget events
    abi = json.loads(abi_path.read_text())
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(distributor_address),
        abi=abi,
    )

    # Determine the block range for ~4 weeks of history
    latest_block = w3.eth.block_number
    # Arbitrum: ~250ms block time → ~4 blocks/sec → ~4 weeks = 4*7*24*3600*4 blocks
    blocks_per_4_weeks = 4 * 7 * 24 * 3600 * 4
    from_block = max(0, latest_block - blocks_per_4_weeks)

    events_found: list[str] = []
    sample_rows: list[dict] = []

    for event_name in _CANDIDATE_EVENT_NAMES:
        try:
            event_filter = getattr(contract.events, event_name, None)
            if event_filter is None:
                continue
            logs = event_filter.get_logs(fromBlock=from_block, toBlock=latest_block)
            if logs:
                events_found.append(event_name)
                for log in logs[:2]:  # sample first 2 events
                    sample_rows.append(
                        {
                            "event": event_name,
                            "block": log["blockNumber"],
                            "args": dict(log["args"]),
                        }
                    )
        except Exception as e:
            # Event doesn't exist on this contract or call failed
            print(f"  {event_name}: {e}", file=sys.stderr)
            continue

    feasible = len(events_found) > 0 and len(sample_rows) >= 4
    verdict = {
        "feasible": feasible,
        "events_found": events_found,
        "sample_reconstructed": sample_rows[:4] if feasible else None,
        "blockers": [] if feasible else ["no_budget_events_found_in_contract_logs"],
        "time_spent_hours": (time.time() - start) / 3600,
    }
    _write_verdict(verdict)
    return 0 if feasible else 0  # exit 0 regardless — infeasible is an expected outcome


def main() -> int:
    ap = argparse.ArgumentParser(
        description="A6 spike — attempt historical E_liq budget reconstruction from distributor events.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip all network calls; write a stub infeasible verdict (for CI smoke tests).",
    )
    args = ap.parse_args()

    if args.dry_run:
        return run_dry_run()
    return run_spike()


if __name__ == "__main__":
    sys.exit(main())
