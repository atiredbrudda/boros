"""Kill-report writer for DATA-09 economics gate halt.

Writes docs/kill-report-YYYYMMDD.md when the economics gate finds an empty shortlist.
The report is a HALTING artifact: operator-readable, fully self-describing, containing
all knobs that drove the halt decision so the situation can be reproduced 3 weeks later.

T-01-12-04 mitigation: no silent halt -- every ProjectHalt writes a timestamped report
with market-by-market R_apr, the threshold used, and the full BotConfig knob tree.

[[Economics kill-switch v0.5]]
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog.contextvars import get_contextvars

# Resolve template path: prefer CWD-relative (production), fall back to repo-root
# discovery (test environments that run pytest from python/ subdirectory).
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[4]  # screener/ -> boros_brain/ -> src/ -> python/ -> boros/
_DEFAULT_TEMPLATE = Path("docs/kill-report-template.md")


def _find_template() -> Path:
    """Resolve kill-report-template.md from CWD or repo root.

    CWD-relative is preferred (production run from boros/ root).
    Falls back to repo-root-relative for test environments that run from python/.
    """
    cwd_relative = Path("docs/kill-report-template.md")
    if cwd_relative.exists():
        return cwd_relative
    repo_relative = _REPO_ROOT / "docs" / "kill-report-template.md"
    if repo_relative.exists():
        return repo_relative
    # If neither exists, return the CWD-relative path so the caller gets a
    # FileNotFoundError pointing at a sensible path (not a hidden fallback).
    return cwd_relative


def write_kill_report(
    rows: list[dict[str, Any]],
    *,
    config: Any,  # BotConfig (avoid circular import by typing as Any)
    threshold: float,
    run_id: str | None = None,
    template_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Write docs/kill-report-YYYYMMDD.md from the kill-report-template.md.

    Parameters
    ----------
    rows:
        List of per-market dicts with keys: market_id, r_apr_on_collateral,
        alt_yield_used, fill_loss_used, threshold, delta, halt_reason.
    config:
        BotConfig instance -- used to dump the full knob tree as JSON.
    threshold:
        Computed alt_yield + fill_loss_coarse_bound value (decimal fraction).
    run_id:
        Active run_id. If None, reads from structlog contextvars (bound by
        configure_logging). Falls back to placeholder if neither is set.
    template_path:
        Override the template path (useful in tests). Defaults to auto-discovery.
    output_dir:
        Override the output directory (useful in tests). Defaults to docs/.

    Returns
    -------
    Path to the written kill-report file.
    """
    resolved_run_id = run_id or get_contextvars().get("run_id", "<current_run_id>")
    resolved_template = template_path or _find_template()
    template = resolved_template.read_text()
    today = datetime.now(UTC)

    # Best-effort git SHA: fallback to "unknown" if git is unavailable
    try:
        git_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_sha = "unknown"

    # Build Markdown table rows
    row_md = "\n".join(
        "| {market_id} | {r_apr:.4f} | {alt:.4f} | {fl:.4f} | {thr:.4f} | {delta:+.4f} | {reason} |".format(
            market_id=r["market_id"],
            r_apr=r["r_apr_on_collateral"],
            alt=r["alt_yield_used"],
            fl=r["fill_loss_used"],
            thr=r["threshold"],
            delta=r["delta"],
            reason=r["halt_reason"],
        )
        for r in rows
    )

    rendered = template.format(
        timestamp_iso=today.isoformat(),
        git_sha=git_sha,
        run_id=resolved_run_id,
        rows=row_md,
        threshold=threshold,
        knob_tree_json=json.dumps(config.model_dump(mode="json"), indent=2),
    )

    out_dir = output_dir if output_dir is not None else Path("docs")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"kill-report-{today.strftime('%Y%m%d')}.md"
    out.write_text(rendered)
    return out
