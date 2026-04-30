#!/usr/bin/env python3
"""OI-vs-maturity proxy audit — Phase 05.2 W0 follow-on.

Tests the maturity-decay hypothesis: does notionalOI on Pendle Boros markets
grow as expiry approaches? OI is the strongest available proxy for "where
Pendle is likely allocating reward budget" since the protocol does not publish
budget history.

Loads market-data NDJSON for the 6 ETH markets at 3 maturities (BINANCE +
HYPERLIQUID × {29MAY, 26JUN, 25SEP} 2026), aggregates daily mean OI, and
plots:
  - Panel A: daily mean OI vs calendar date, all 6 markets
  - Panel B: daily mean OI vs days-to-expiry, all 6 markets overlapped

Verdict labels:
  - oi_ramps_toward_expiry: shorter-maturity markets show accelerating OI
    relative to longer-maturity markets in the same calendar window
  - oi_flat_across_maturity: no discernible relationship; reward-budget choice
    on sept25 binding market is structurally fine
  - inconclusive: data span too short to differentiate

Output: var/audit/oi_vs_maturity.png + var/reports/oi_vs_maturity_verdict.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
NDJSON_ROOT = REPO_ROOT / "data" / "ndjson" / "market-data"
OUT_PNG = REPO_ROOT / "var" / "audit" / "oi_vs_maturity.png"
OUT_JSON = REPO_ROOT / "var" / "reports" / "oi_vs_maturity_verdict.json"

# (numeric_id_prefix, human_name, expiry_iso, venue, maturity_label)
MARKETS = [
    ("112", "BINANCE-ETHUSDT-29MAY2026", "2026-05-29", "BINANCE", "28d"),
    ("76", "BINANCE-ETHUSDT-26JUN2026", "2026-06-26", "BINANCE", "56d"),
    ("101", "BINANCE-ETHUSDT-25SEP2026", "2026-09-25", "BINANCE", "147d"),
    ("113", "HYPERLIQUID-ETH-29MAY2026", "2026-05-29", "HYPERLIQUID", "28d"),
    ("74", "HYPERLIQUID-ETH-26JUN2026", "2026-06-26", "HYPERLIQUID", "56d"),
    ("102", "HYPERLIQUID-ETH-25SEP2026", "2026-09-25", "HYPERLIQUID", "147d"),
]

VENUE_COLOR = {"BINANCE": "tab:blue", "HYPERLIQUID": "tab:orange"}
MATURITY_LINESTYLE = {"28d": "-", "56d": "--", "147d": ":"}


def load_market_oi(numeric_id: str, human_name: str, expiry_iso: str) -> pl.DataFrame:
    """Load NDJSON for one market, aggregate hourly→daily mean OI, add days_to_expiry."""
    market_dir = NDJSON_ROOT / f"{numeric_id}-{human_name}"
    files = sorted(market_dir.glob("*.ndjson"))
    if not files:
        return pl.DataFrame()
    expiry_dt = datetime.strptime(expiry_iso, "%Y-%m-%d").replace(tzinfo=UTC)

    frames = []
    for f in files:
        df = pl.read_ndjson(f).select(
            [
                pl.col("timestamp").cast(pl.Int64),
                pl.col("notionalOI").cast(pl.Float64),
            ]
        )
        frames.append(df)
    raw = pl.concat(frames)
    daily = (
        raw.with_columns(
            pl.from_epoch(pl.col("timestamp"), time_unit="s").alias("ts")
        )
        .with_columns(pl.col("ts").dt.date().alias("date"))
        .group_by("date")
        .agg(pl.col("notionalOI").mean().alias("oi_eth"))
        .sort("date")
    )
    # Compute days_to_expiry per row
    daily = daily.with_columns(
        ((pl.lit(expiry_dt.timestamp()) - pl.col("date").cast(pl.Datetime).dt.timestamp("ms") / 1000) / 86400.0)
        .cast(pl.Int64)
        .alias("days_to_expiry")
    )
    return daily


def main() -> int:
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    market_data = {}
    for numeric_id, human_name, expiry_iso, venue, mat_label in MARKETS:
        df = load_market_oi(numeric_id, human_name, expiry_iso)
        if df.is_empty():
            print(f"[skip] no NDJSON for {human_name}")
            continue
        market_data[human_name] = {
            "df": df,
            "venue": venue,
            "maturity": mat_label,
            "expiry": expiry_iso,
        }

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(16, 6))

    summary = {}
    for name, m in market_data.items():
        df = m["df"]
        color = VENUE_COLOR[m["venue"]]
        ls = MATURITY_LINESTYLE[m["maturity"]]
        label = f"{m['venue']} {m['maturity']}"

        # Panel A: OI over calendar time
        dates = [datetime.combine(d, datetime.min.time()) for d in df["date"].to_list()]
        oi = df["oi_eth"].to_numpy()
        ax_a.plot(dates, oi, color=color, linestyle=ls, label=label, lw=1.4)

        # Panel B: OI vs days_to_expiry
        dte = df["days_to_expiry"].to_numpy()
        ax_b.plot(dte, oi, color=color, linestyle=ls, label=label, lw=1.4)

        # Compute growth metrics
        first = float(oi[0]) if len(oi) > 0 else 0.0
        last = float(oi[-1]) if len(oi) > 0 else 0.0
        peak = float(oi.max()) if len(oi) > 0 else 0.0
        median = float(pl.Series(oi).median()) if len(oi) > 0 else 0.0
        n_days = len(oi)
        growth_pct = ((last - first) / first * 100.0) if first > 0 else float("nan")
        # Average daily growth in absolute ETH terms over the window
        oi_per_day = (last - first) / max(1, n_days - 1)
        summary[name] = {
            "venue": m["venue"],
            "maturity_label": m["maturity"],
            "expiry": m["expiry"],
            "n_days": n_days,
            "first_oi_eth": first,
            "last_oi_eth": last,
            "peak_oi_eth": peak,
            "median_oi_eth": median,
            "growth_pct": growth_pct,
            "oi_per_day_eth": oi_per_day,
            "min_days_to_expiry": int(dte.min()) if len(dte) > 0 else None,
            "max_days_to_expiry": int(dte.max()) if len(dte) > 0 else None,
        }

    ax_a.set_xlabel("Calendar date")
    ax_a.set_ylabel("Daily mean notionalOI (ETH)")
    ax_a.set_title("Panel A: OI over calendar time")
    ax_a.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax_a.legend(loc="upper left", fontsize=8)
    ax_a.grid(True, alpha=0.3)

    ax_b.set_xlabel("Days to expiry (smaller = closer to maturity)")
    ax_b.set_ylabel("Daily mean notionalOI (ETH)")
    ax_b.set_title("Panel B: OI vs days-to-expiry (overlapped maturities)")
    ax_b.invert_xaxis()  # so closer-to-expiry is on the right
    ax_b.legend(loc="upper right", fontsize=8)
    ax_b.grid(True, alpha=0.3)

    fig.suptitle("OI-vs-maturity proxy audit — Phase 05.2 W0", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=110)
    plt.close(fig)

    # Verdict logic — compare growth rates by maturity bucket
    binance_28d = summary.get("BINANCE-ETHUSDT-29MAY2026", {})
    binance_56d = summary.get("BINANCE-ETHUSDT-26JUN2026", {})
    binance_147d = summary.get("BINANCE-ETHUSDT-25SEP2026", {})

    growth_28 = binance_28d.get("oi_per_day_eth", 0.0) or 0.0
    growth_56 = binance_56d.get("oi_per_day_eth", 0.0) or 0.0
    growth_147 = binance_147d.get("oi_per_day_eth", 0.0) or 0.0

    # If the 28d market grows fastest in the same calendar window, that's
    # evidence of maturity-attraction (assuming all 3 markets had similar
    # initial conditions when the data window started).
    if growth_28 > 2 * growth_147 and growth_56 > growth_147:
        verdict_label = "oi_ramps_toward_expiry"
        verdict_note = (
            f"BINANCE 28d daily OI growth {growth_28:.2f} ETH/day vs 147d {growth_147:.2f} ETH/day "
            f"(28d growing >2× as fast as 147d). Suggests budget likely follows OI toward expiry — "
            f"sept25 binding market may ramp up as it ages."
        )
    elif abs(growth_28 - growth_147) / max(abs(growth_147), 1.0) < 0.2:
        verdict_label = "oi_flat_across_maturity"
        verdict_note = (
            f"BINANCE 28d daily OI growth {growth_28:.2f} ETH/day vs 147d {growth_147:.2f} ETH/day "
            f"(within 20%). No evidence of maturity-driven OI ramp. Reward-budget pattern likely "
            f"static; sept25 binding market choice should be revisited on current-budget grounds."
        )
    else:
        verdict_label = "inconclusive"
        verdict_note = (
            f"BINANCE growth rates: 28d={growth_28:.2f}, 56d={growth_56:.2f}, 147d={growth_147:.2f} "
            f"(ETH/day). Pattern not clearly monotonic; data span ~2 months may be too short."
        )

    verdict = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "verdict_label": verdict_label,
        "verdict_note": verdict_note,
        "growth_eth_per_day": {
            "binance_28d": growth_28,
            "binance_56d": growth_56,
            "binance_147d": growth_147,
        },
        "level_oi_eth_at_window_end": {
            "binance_28d": binance_28d.get("last_oi_eth", 0.0),
            "binance_56d": binance_56d.get("last_oi_eth", 0.0),
            "binance_147d": binance_147d.get("last_oi_eth", 0.0),
        },
        "per_market": summary,
        "png_path": str(OUT_PNG),
    }
    OUT_JSON.write_text(json.dumps(verdict, indent=2))
    print(f"PNG: {OUT_PNG}")
    print(f"Verdict: {OUT_JSON}")
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
