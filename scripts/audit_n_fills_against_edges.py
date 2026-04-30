#!/usr/bin/env python3
"""E4 audit — Phase 05.2 Wave 0 — n_fills=0 hypothesis test.

Loads BINANCE-ETHUSDT-25SEP2026 trade tape for the binding 26-day window,
computes implied APR series from the trade `rate` field, plots it against
our long-edge (0.74%) and short-edge (1.26%) edge placements, and writes a
verdict JSON + PNG artifact + wiki page entry.

Verdict labels:
  - real_no_fills: APR series never crossed the edges within the window
  - sim_bug_under_counting: APR crossed edges but engine reported n_fills=0
  - inconclusive: data sparse, can't determine

Output:
  var/audit/n_fills_audit_<DATE>.png
  var/reports/n_fills_audit_verdict.json

Resolves CONTEXT.md Wave 0 task E4. Wiki: [[n-fills-zero-binding-window-audit]].
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
PARQUET_ROOT = REPO_ROOT / "data" / "parquet"
OUT_PNG_DIR = REPO_ROOT / "var" / "audit"
OUT_JSON = REPO_ROOT / "var" / "reports" / "n_fills_audit_verdict.json"


def load_implied_apr_series(parquet_root: Path, market_id: str, days: int) -> pl.DataFrame:
    """Returns DataFrame[blockTimestamp: i64, implied_apr_pct: f64] sorted by blockTimestamp."""
    trades_dir = parquet_root / "market_trades"
    df = (
        pl.scan_parquet(str(trades_dir / "**" / "*.parquet"))
        .filter(pl.col("market_id").str.contains(market_id))
        .select(
            [
                pl.col("blockTimestamp").cast(pl.Int64),
                (pl.col("rate").cast(pl.Float64) * 100.0).alias("implied_apr_pct"),
            ]
        )
        .sort("blockTimestamp")
        .collect()
    )
    if df.is_empty():
        return df
    # Last `days` of data
    last_ts = df["blockTimestamp"].max()
    cutoff = last_ts - days * 86400
    return df.filter(pl.col("blockTimestamp") >= cutoff)


def plot_apr_vs_edges(
    df: pl.DataFrame,
    edge_lo_pct: float,
    edge_hi_pct: float,
    out_png: Path,
) -> dict[str, Any]:
    """Plot implied APR series with horizontal edge lines; return summary stats."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if df.is_empty():
        return {
            "n_crossings_lo": 0,
            "n_crossings_hi": 0,
            "max_apr_pct": 0.0,
            "min_apr_pct": 0.0,
            "mean_apr_pct": 0.0,
        }
    ts = df["blockTimestamp"].to_numpy()
    apr = df["implied_apr_pct"].to_numpy()
    # Crossings = sign-change count vs each edge
    n_crossings_lo = int(((apr[:-1] - edge_lo_pct) * (apr[1:] - edge_lo_pct) < 0).sum())
    n_crossings_hi = int(((apr[:-1] - edge_hi_pct) * (apr[1:] - edge_hi_pct) < 0).sum())
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(ts, apr, lw=0.5, alpha=0.7, label="Implied APR (%)")
    ax.axhline(edge_lo_pct, color="green", lw=1, ls="--", label=f"Long edge {edge_lo_pct}%")
    ax.axhline(edge_hi_pct, color="red", lw=1, ls="--", label=f"Short edge {edge_hi_pct}%")
    ax.set_xlabel("blockTimestamp")
    ax.set_ylabel("Implied APR (%)")
    ax.set_title(
        f"E4 audit — APR series vs edges ({n_crossings_lo} lo / {n_crossings_hi} hi crossings)"
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_png, dpi=100)
    plt.close(fig)
    return {
        "n_crossings_lo": n_crossings_lo,
        "n_crossings_hi": n_crossings_hi,
        "max_apr_pct": float(apr.max()),
        "min_apr_pct": float(apr.min()),
        "mean_apr_pct": float(apr.mean()),
    }


def classify_verdict(stats: dict[str, Any], edge_lo_pct: float, edge_hi_pct: float) -> str:
    if stats["n_crossings_lo"] == 0 and stats["n_crossings_hi"] == 0:
        # APR never crossed either edge — real no-fills outcome
        if stats["max_apr_pct"] < edge_lo_pct or stats["min_apr_pct"] > edge_hi_pct:
            return "real_no_fills"
        return "inconclusive"
    # Crossings observed but engine reported n_fills=0 → sim bug
    return "sim_bug_under_counting"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--market", default="BINANCE-ETHUSDT-25SEP2026")
    p.add_argument("--days", type=int, default=26)
    p.add_argument("--edge-lo-pct", type=float, default=0.74)
    p.add_argument("--edge-hi-pct", type=float, default=1.26)
    p.add_argument("--parquet-root", default=str(PARQUET_ROOT))
    args = p.parse_args(argv)

    df = load_implied_apr_series(Path(args.parquet_root), args.market, args.days)
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    out_png = OUT_PNG_DIR / f"n_fills_audit_{date_str}.png"
    stats = plot_apr_vs_edges(df, args.edge_lo_pct, args.edge_hi_pct, out_png)
    verdict_label = classify_verdict(stats, args.edge_lo_pct, args.edge_hi_pct)
    verdict = {
        "market_id": args.market,
        "window_days": args.days,
        "edge_lo_pct": args.edge_lo_pct,
        "edge_hi_pct": args.edge_hi_pct,
        "n_rows_scanned": int(df.shape[0]),
        **stats,
        "verdict_label": verdict_label,
        "png_path": str(out_png),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(verdict, indent=2))
    print(f"PNG: {out_png}")
    print(f"Verdict: {OUT_JSON}")
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
