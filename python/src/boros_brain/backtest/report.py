"""BACK-05: backtest output writer + plot generators.

Output layout (Hive-partitioned, one BacktestRunOutput row per parquet):
    data/parquet/backtest_results/run_id=<ulid>/
      |-- sweep_axis=base/results.parquet
      |-- sweep_axis=cancel_latency/sweep_value=<L>/results.parquet
      |-- sweep_axis=competition/sweep_value=<m>/results.parquet
      |-- sweep_axis=forfeit_branch/sweep_value=<benign|punitive>/results.parquet
      |-- sweep_axis=perturbation/sweep_value=<knob_path>/results.parquet
      |-- bootstrap/results.parquet
      |-- ship_gate_verdict.json
      |-- lineage_a_b_row.json
      |-- plots/{calibration,dpnl_dl,dpnl_dq}.png

Plot generation is a SEPARATE subcommand (Plan 05-09: `python -m boros_brain.backtest plot --run-id <ulid>`).
The replay engine has no plotting dependency — replay determinism is unaffected
by matplotlib version drift.

Path-traversal guard mirrors loss_model/artifact.py:51-62 — operator-controlled
sweep_value values cannot escape parquet_root.

[[backtest-output-schema-and-parquet-partitioning]]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from .schemas import BacktestRunOutput

log = structlog.get_logger(__name__)


def _ensure_under_root(out_dir: Path, parquet_root_resolved: Path) -> None:
    """Path-traversal guard. Raise ValueError if out_dir escapes parquet_root."""
    if not out_dir.is_relative_to(parquet_root_resolved):
        raise ValueError(f"backtest_results path traversal blocked: {out_dir} " f"is outside {parquet_root_resolved}")


def write_backtest_row(
    row: BacktestRunOutput,
    *,
    parquet_root: Path = Path("data/parquet/backtest_results"),
) -> Path:
    """Write a single output row to its Hive-partitioned location.

    Path-traversal guard pattern copied verbatim from loss_model/artifact.py:51-61.
    """
    parquet_root_resolved = parquet_root.resolve()
    out_dir = parquet_root / f"run_id={row.run_id}" / f"sweep_axis={row.sweep_axis}"
    if row.sweep_axis != "base":
        out_dir = out_dir / f"sweep_value={row.sweep_value}"
    out_dir = out_dir.resolve()
    _ensure_under_root(out_dir, parquet_root_resolved)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "results.parquet"
    pl.DataFrame([row.model_dump(mode="json")]).write_parquet(out_path)
    log.info(
        "backtest.row_written",
        run_id=row.run_id,
        sweep_axis=row.sweep_axis,
        sweep_value=row.sweep_value,
        parquet=str(out_path),
    )
    return out_path


def write_ship_gate_verdict_json(
    verdict: Any,  # ShipGateVerdict — forward-ref to Plan 05-07
    *,
    parquet_root: Path = Path("data/parquet/backtest_results"),
) -> Path:
    """Write ship_gate_verdict.json to <parquet_root>/run_id=<run_id>/."""
    parquet_root_resolved = parquet_root.resolve()
    out_dir = (parquet_root / f"run_id={verdict.manifest_run_id}").resolve()
    _ensure_under_root(out_dir, parquet_root_resolved)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ship_gate_verdict.json"
    path.write_text(json.dumps(verdict.model_dump(mode="json"), indent=2))
    log.info(
        "backtest.ship_gate_verdict_written",
        run_id=verdict.manifest_run_id,
        path=str(path),
    )
    return path


def write_lineage_a_b_row(
    a_row: BacktestRunOutput,
    b_row: BacktestRunOutput,
    *,
    parquet_root: Path = Path("data/parquet/backtest_results"),
) -> Path:
    """Write the operator-vintage vs pessimistic-haircut A/B summary (B6 absorption)."""
    parquet_root_resolved = parquet_root.resolve()
    out_dir = (parquet_root / f"run_id={a_row.run_id}").resolve()
    _ensure_under_root(out_dir, parquet_root_resolved)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "lineage_a_b_row.json"
    path.write_text(
        json.dumps(
            {
                "operator_vintage": a_row.model_dump(mode="json"),
                "pessimistic_haircut": b_row.model_dump(mode="json"),
            },
            indent=2,
        )
    )
    return path


def plot_calibration(rows: list[BacktestRunOutput], *, out_path: Path) -> Path:
    """Calibration plot: predicted_p_fill_mean vs realized_fill_rate."""
    import matplotlib  # noqa: PLC0415 — lazy import

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    pred = [r.predicted_p_fill_mean for r in rows]
    realized = [r.realized_fill_rate for r in rows]
    ax.scatter(pred, realized, alpha=0.6)
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="ideal")
    ax.set_xlabel("predicted P(fill) mean")
    ax.set_ylabel("realized fill rate")
    ax.set_title("Calibration plot")
    ax.legend()
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_dpnl_dl(slopes: list[tuple[float, float]], *, out_path: Path) -> Path:
    """dP&L/dL line plot."""
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    if slopes:
        L = [p[0] for p in slopes]
        dPnL = [p[1] for p in slopes]
        ax.plot(L, dPnL, marker="o")
    ax.axhline(0, color="k", linestyle=":", linewidth=0.5)
    ax.set_xlabel("L (cancel latency, seconds)")
    ax.set_ylabel("dP&L / dL (annualized %, per second of L)")
    ax.set_title("Cancel-latency sensitivity (BACK-03)")
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_dpnl_dq(slopes: list[tuple[float, float]], *, out_path: Path) -> Path:
    """dP&L/dQ_competing line plot."""
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    if slopes:
        m = [p[0] for p in slopes]
        dPnL = [p[1] for p in slopes]
        ax.plot(m, dPnL, marker="o")
    ax.axhline(0, color="k", linestyle=":", linewidth=0.5)
    ax.set_xlabel("m (competition multiplier)")
    ax.set_ylabel("dP&L / dm (annualized %, per unit of m)")
    ax.set_title("Competition sensitivity (BACK-04)")
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return out_path


def append_perturbation_section_to_ship_gate_report(
    report_path: Path,
    rows: list[Any],  # list[PerturbationRow] — type forward-ref to avoid circular import
    *,
    n_fragile_threshold: int = 0,
) -> Path:
    """BACK-08: append a `## Perturbation Grid` section to ship-gate-report.md.

    Per BACK-08 ROADMAP scope: "sign-flipping on any knob is a fragility flag in
    the ship-gate report." This function is the implementation of "in the
    ship-gate report" — it APPENDS to var/backtest/<run_id>/ship-gate-report.md
    written by ship_gate.write_ship_gate_report.

    Sign-flip is RECORDED, not an automatic ship-gate fail (RESEARCH.md L1045 —
    operator decides). `n_fragile_threshold` is a future hook for operator
    policy; default 0 means "report all flags, never auto-fail."
    """
    if not report_path.exists():
        raise FileNotFoundError(
            f"ship-gate report not found at {report_path}; " "run ship_gate.write_ship_gate_report first"
        )
    n_fragile = sum(1 for r in rows if r.fragile)
    lines = [
        "",
        "## Perturbation Grid (BACK-08)",
        "",
        f"- Total numeric leaves perturbed: **{len(rows)}**",
        f"- Fragile knobs (sign-flip on ±perturbation_pct): **{n_fragile}**",
        "",
        "> **Note:** Sign-flip is RECORDED, not an automatic ship-gate fail.",
        "> The operator decides whether to ship under flagged fragility.",
        "",
        "| knob_path | unperturbed_p5 | low_p5 (−pct) | high_p5 (+pct) | fragile |",
        "|-----------|----------------|---------------|----------------|---------|",
    ]
    for r in rows:
        flag = "**YES**" if r.fragile else "no"
        lines.append(
            f"| `{r.knob_path}` | {r.baseline_p5_pnl:.4f} | " f"{r.low_p5_pnl:.4f} | {r.high_p5_pnl:.4f} | {flag} |"
        )
    lines.append("")
    addendum = "\n".join(lines)
    with report_path.open("a") as f:
        f.write(addendum)
    log.info(
        "ship_gate.perturbation_section_appended",
        path=str(report_path),
        n_rows=len(rows),
        n_fragile=n_fragile,
    )
    return report_path


__all__ = [
    "write_backtest_row",
    "write_ship_gate_verdict_json",
    "write_lineage_a_b_row",
    "plot_calibration",
    "plot_dpnl_dl",
    "plot_dpnl_dq",
    "append_perturbation_section_to_ship_gate_report",
]
