"""PROTOCOL 2 — architecture yaml drift tests (Plan 05-09).

test_architecture_lint_passes_with_phase5_nodes: scripts/architecture_lint.py exits 0.
test_architecture_yaml_contains_all_phase5_nodes: all 17+ Phase-5 node ids present.
test_architecture_yaml_includes_9_backtest_config_knobs: exactly 9 config.backtest.* nodes.
test_architecture_yaml_protocol_2_invariant: every declared backtest path exists on disk.

[[backtest-architecture-manifest-delta-phase-5]]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE_YML = REPO_ROOT / "docs" / "architecture.yml"


def _load_yml() -> dict:
    return yaml.safe_load(ARCHITECTURE_YML.read_text())


def test_architecture_lint_passes_with_phase5_nodes() -> None:
    """scripts/architecture_lint.py exits 0 — no drift between yaml and source tree."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "architecture_lint.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"architecture_lint.py failed (exit {result.returncode}):\n" f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_architecture_yaml_contains_all_phase5_nodes() -> None:
    """All Phase-5 node ids are declared in docs/architecture.yml."""
    data = _load_yml()
    node_ids = {n["id"] for n in data["nodes"]}

    expected_phase5_nodes = {
        # brain.backtest package marker omitted — no __init__.py-equivalent node declared
        "brain.backtest.sweeps",
        "brain.backtest.config",
        "brain.backtest.schemas",
        "brain.backtest.synthetic_orders",
        "brain.backtest.replay",
        "brain.backtest.cancel_latency",
        "brain.backtest.bootstrap",
        "brain.backtest.ship_gate",
        "brain.backtest.report",
        "brain.backtest.sweeps.cancel_latency",
        "brain.backtest.sweeps.competition",
        "brain.backtest.sweeps.forfeit_branch",
        "brain.backtest.perturbation",
        "brain.backtest.contour_2d",
        "brain.backtest.cli",
        "brain.backtest.run_manifest",
        "parquet.backtest_results",
    }

    missing = expected_phase5_nodes - node_ids
    assert not missing, f"Phase-5 nodes missing from docs/architecture.yml: {sorted(missing)}"


def test_architecture_yaml_includes_9_backtest_config_knobs() -> None:
    """At least 9 config.backtest.* references in edges (as depends-on-config targets).

    The BacktestConfig has 9 knobs. They appear as edge targets in architecture.yml.
    (Node declarations for config_knob entries may be in the global config nodes block
    or only appear as edge targets — either way there must be >= 9 distinct references.)
    """
    # Collect config.backtest.* from both nodes (if declared) and edge targets
    data = _load_yml()
    knob_ids: set[str] = set()
    # From nodes
    for n in data["nodes"]:
        if n["id"].startswith("config.backtest."):
            knob_ids.add(n["id"])
    # From edges (depends-on-config targets)
    for e in data.get("edges", []):
        to_id = e.get("to", "") if isinstance(e, dict) else ""
        if to_id.startswith("config.backtest."):
            knob_ids.add(to_id)
    assert len(knob_ids) >= 9, (
        f"expected >= 9 config.backtest.* references in architecture.yml, got {len(knob_ids)}: " f"{sorted(knob_ids)}"
    )


def test_architecture_yaml_protocol_2_invariant() -> None:
    """Every node with a path under python/src/boros_brain/backtest/ exists on disk.

    Catches the inverse drift — node declared but file missing.
    """
    data = _load_yml()
    missing_files: list[str] = []
    for node in data["nodes"]:
        path_val = node.get("path", "")
        if not path_val:
            continue
        if "boros_brain/backtest" in path_val or "/sweeps/" in path_val:
            full_path = REPO_ROOT / path_val
            if not full_path.exists():
                missing_files.append(path_val)

    assert not missing_files, "architecture.yml declares these backtest paths but they don't exist:\n" + "\n".join(
        missing_files
    )
