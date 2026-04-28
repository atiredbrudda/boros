"""BACK-* PROTOCOL 3 (CLAUDE.md): backtest-local RUN_MANIFEST sidecar emitter.

Writes `var/backtest/<run_id>/<run_id>.manifest.json` (separate from the broader
project-wide `logs/<YYYY-MM-DD>/<run_id>.manifest.json` written by
manifest/writer.write_manifest). Both files contain identical content; the
backtest-local copy is what operators look for next to ship-gate-report.md.

Per CLAUDE.md Engineering Protocol 3: "RUN_MANIFEST first log line + sidecar
JSON + run_manifests SQLite row, all three identical content." This module
handles the second of the three (sidecar JSON); the first (first log line)
is handled by cli.main; the third (SQLite row) is handled by
manifest/writer.write_manifest.

Adding a knob to BotConfig surfaces in BOTH the perturbation grid (Plan 05-08)
AND the manifest sidecar — assert_manifest_contains_all_botconfig_leaves is
the lockstep guard.

[[backtest-cli-and-run-manifest-emission]]
[[run-manifest-writer]]
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..manifest.schema import RunManifest

log = structlog.get_logger(__name__)


def _ensure_under_root(out_dir: Path, root_resolved: Path) -> None:
    """Raise ValueError if out_dir escapes root_resolved."""
    if not out_dir.is_relative_to(root_resolved):
        raise ValueError(f"backtest manifest sidecar path traversal blocked: {out_dir} " f"is outside {root_resolved}")


def emit_backtest_manifest(
    manifest: RunManifest,
    *,
    run_id: str,
    output_dir: Path,
) -> Path:
    """Atomic-write `<output_dir>/<run_id>.manifest.json`.

    Path-traversal guard mirrors loss_model/artifact.py:51-62 — defensive
    against any future operator-supplied path component.

    Returns the path written.
    """
    # Resolve var_root from __file__ so this works regardless of CWD
    # (e.g. when invoked via `uv run --directory python`).
    # python/src/boros_brain/backtest/run_manifest.py → parents[4] = repo root
    _repo_root = Path(__file__).resolve().parents[4]
    var_root = (_repo_root / "var/backtest").resolve()
    output_dir = output_dir.resolve()
    _ensure_under_root(output_dir, var_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{run_id}.manifest.json"

    payload = json.dumps(manifest.model_dump(mode="json"), indent=2)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{run_id}.manifest.",
        suffix=".json.tmp",
        dir=str(output_dir),
    )
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(payload)
        Path(tmp_name).replace(target)
    except Exception:
        # Cleanup on failure
        if Path(tmp_name).exists():
            Path(tmp_name).unlink(missing_ok=True)
        raise
    log.info("backtest.manifest.sidecar_written", path=str(target), run_id=run_id)
    return target


def assert_manifest_contains_all_botconfig_leaves(
    manifest: RunManifest,
    config: BotConfig,
) -> None:
    """PROTO-04 forcing function: every numeric BotConfig leaf is in the manifest.

    Reuses the perturbation reflection idiom (Plan 05-08); adding a knob to
    BotConfig surfaces in both the perturbation grid AND the manifest in
    lockstep. Used by test_backtest_run_manifest_first_log.py to prove the
    discipline at runtime.

    NOTE: exclude_prefixes=() — manifest contains ALL leaves including
    BotConfig.backtest.* (perturbation excludes them by design; manifest does
    not). This is intentional: the backtest meta-knobs must appear in the
    manifest so reproducibility is preserved across `bootstrap_n_resamples`
    changes.
    """
    from .perturbation import enumerate_perturbable_leaves

    expected = {leaf.path for leaf in enumerate_perturbable_leaves(config, exclude_prefixes=())}

    seen: set[str] = set()

    def _walk(d: object, path: list[str]) -> None:
        if isinstance(d, dict):
            for k, v in d.items():
                _walk(v, path + [k])
        elif isinstance(d, list):
            for i, v in enumerate(d):
                _walk(v, path + [str(i)])
        elif isinstance(d, int | float) and not isinstance(d, bool):
            seen.add(".".join(path))

    _walk(manifest.config, [])

    missing = expected - seen
    extra = seen - expected
    if missing or extra:
        raise AssertionError(
            f"manifest config drifts from BotConfig reflection. " f"missing={sorted(missing)} extra={sorted(extra)}"
        )


__all__ = [
    "emit_backtest_manifest",
    "assert_manifest_contains_all_botconfig_leaves",
]
