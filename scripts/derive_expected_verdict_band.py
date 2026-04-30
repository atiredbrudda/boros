#!/usr/bin/env python3
"""Phase 05.3 Plan 02 T3 — derive expected USD-APR verdict band.

Produces ``var/reports/expected_verdict_band_<DATE>.json`` for the binding
ship-gate re-run, consumed by Phase 05.3 Plan 01 T7 (verdict classification).

Formula (per `[[pendle-lo-reward-formula-verified]]`)::

    share = q_me / (sigma_others + q_me)
    r_share_per_epoch_pendle = e_liq_per_epoch * side_split * share
    r_apr_usd_on_collateral = r_share_per_epoch_pendle * 52 * pendle_price_usd / collateral_usd

The band is computed by sweeping the parameter grid:

    sigma_others ∈ {dapp-anchor values}
        ∪ {parquet-snapshot values at start/mid/end of replay window} (if --sigma-source parquet)
    side_split   ∈ {prior_epoch_split, current_epoch_split}
    q_me         ∈ {q_max - 20%, q_max, q_max + 20%}

Outputs ``(low, mid, high)`` over the full grid, plus the full per-cell table.

CLI::

    uv run python scripts/derive_expected_verdict_band.py \\
        --market BINANCE-ETHUSDT-25SEP2026 \\
        --side long \\
        --config strategy/v0.5-phase05.1-shortlist.yaml \\
        --epoch both \\
        --sigma-source dapp \\
        --out-json var/reports/expected_verdict_band_2026-04-30.json

Determinism: same inputs → same outputs to 1e-9 relative tolerance. No randomness;
no ``time.time()`` (chain_ts only). Smoke test in ``scripts/test_derive_expected_verdict_band.py``.

Wiki: [[expected-verdict-band-2026-04-30]], [[dapp-apr-reconciliation-2026-04-30]],
      [[pendle-lo-reward-formula-verified]].
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EPOCHS_PER_YEAR = 52  # matches `economics_gate.EPOCHS_PER_YEAR`

# ── Dapp-anchor sigma values from [[dapp-apr-reconciliation-2026-04-30]] ────
# These are the defensible bracket *without* parquet-empirical readings.
# Each anchor is a (label, sigma_yu) pair; the wiki page documents derivation.
_DAPP_SIGMA_ANCHORS_LONG: dict[str, float] = {
    "context_md_75":            75.0,   # CONTEXT.md old "effective pool" assumption (RETRACTED, retained as conservative-low scenario)
    "raw_orderbook_in_range":  165.0,   # raw `order_book_raw` cumulative-in-CLO-band sum; reproduces 489% badge to ±2%
    "dapp_estimator_implicit": 329.0,   # dapp's "While Active/day" implicit denominator at t+11.5h (likely the realistic value)
}
_DAPP_SIGMA_ANCHORS_SHORT: dict[str, float] = {
    "context_md_310":          310.0,
    "raw_orderbook_in_range":  198.0,
    "dapp_estimator_implicit": 211.0,
}


@dataclass(frozen=True)
class BandInputs:
    """All numeric inputs to the band derivation."""

    market: str
    side: str
    epoch: str  # "prior", "current", or "both"
    sigma_yu_anchors: dict[str, float]
    side_split_prior: float
    side_split_current: float
    q_max_yu: float
    q_me_grid_yu: tuple[float, ...]
    e_liq_per_epoch_pendle: float
    pendle_price_usd: float
    collateral_usd: float
    sigma_source: str  # "dapp" | "parquet" | "both"


@dataclass(frozen=True)
class BandCell:
    """One (sigma, side_split, q_me) grid cell + computed APR."""

    sigma_label: str
    sigma_yu: float
    epoch: str
    side_split: float
    q_me_yu: float
    share: float
    r_share_per_epoch_pendle: float
    r_share_per_year_pendle: float
    r_apr_usd_fraction: float


@dataclass
class BandOutput:
    """Top-level JSON output."""

    market: str
    side: str
    derivation_date_utc: str
    formula_source_wiki: str
    sigma_source: str
    inputs: dict[str, Any]
    cells: list[dict[str, Any]] = field(default_factory=list)
    low_apr: float = 0.0
    mid_apr: float = 0.0
    high_apr: float = 0.0
    notes: list[str] = field(default_factory=list)


# ── Pure compute (covered by smoke test) ────────────────────────────────────


def compute_share(q_me_yu: float, sigma_yu: float) -> float:
    """share = q_me / (sigma + q_me) — matches `economics_gate.compute_r_apr_on_collateral_pendle`."""
    if q_me_yu <= 0.0:
        return 0.0
    return q_me_yu / (sigma_yu + q_me_yu)


def compute_apr_usd_fraction(
    *,
    q_me_yu: float,
    sigma_yu: float,
    side_split: float,
    e_liq_per_epoch_pendle: float,
    pendle_price_usd: float,
    collateral_usd: float,
) -> float:
    """Compute the annualized USD-APR fraction (0.30 = 30%) for one grid cell."""
    if collateral_usd <= 0.0:
        raise ValueError("collateral_usd must be positive")
    share = compute_share(q_me_yu, sigma_yu)
    r_share_per_epoch_pendle = e_liq_per_epoch_pendle * side_split * share
    r_share_per_year_pendle = r_share_per_epoch_pendle * EPOCHS_PER_YEAR
    return r_share_per_year_pendle * pendle_price_usd / collateral_usd


def derive_band(inputs: BandInputs, derivation_date_utc: str) -> BandOutput:
    """Sweep the parameter grid; return BandOutput with low/mid/high + per-cell list."""
    epochs: list[tuple[str, float]] = []
    if inputs.epoch in ("prior", "both"):
        epochs.append(("prior", inputs.side_split_prior))
    if inputs.epoch in ("current", "both"):
        epochs.append(("current", inputs.side_split_current))
    if not epochs:
        raise ValueError(f"unknown epoch={inputs.epoch!r}; expected prior|current|both")

    cells: list[BandCell] = []
    for (sigma_label, sigma_yu), (epoch_name, side_split), q_me_yu in product(
        inputs.sigma_yu_anchors.items(), epochs, inputs.q_me_grid_yu
    ):
        share = compute_share(q_me_yu, sigma_yu)
        r_share_per_epoch_pendle = inputs.e_liq_per_epoch_pendle * side_split * share
        r_share_per_year_pendle = r_share_per_epoch_pendle * EPOCHS_PER_YEAR
        r_apr_usd_fraction = (
            r_share_per_year_pendle * inputs.pendle_price_usd / inputs.collateral_usd
        )
        cells.append(
            BandCell(
                sigma_label=sigma_label,
                sigma_yu=sigma_yu,
                epoch=epoch_name,
                side_split=side_split,
                q_me_yu=q_me_yu,
                share=share,
                r_share_per_epoch_pendle=r_share_per_epoch_pendle,
                r_share_per_year_pendle=r_share_per_year_pendle,
                r_apr_usd_fraction=r_apr_usd_fraction,
            )
        )

    aprs = sorted(c.r_apr_usd_fraction for c in cells)
    low = aprs[0]
    high = aprs[-1]
    mid = aprs[len(aprs) // 2]

    out = BandOutput(
        market=inputs.market,
        side=inputs.side,
        derivation_date_utc=derivation_date_utc,
        formula_source_wiki="pendle-lo-reward-formula-verified",
        sigma_source=inputs.sigma_source,
        inputs={
            "epoch": inputs.epoch,
            "sigma_yu_anchors": dict(inputs.sigma_yu_anchors),
            "side_split_prior": inputs.side_split_prior,
            "side_split_current": inputs.side_split_current,
            "q_max_yu": inputs.q_max_yu,
            "q_me_grid_yu": list(inputs.q_me_grid_yu),
            "e_liq_per_epoch_pendle": inputs.e_liq_per_epoch_pendle,
            "pendle_price_usd": inputs.pendle_price_usd,
            "collateral_usd": inputs.collateral_usd,
        },
        cells=[
            {
                "sigma_label": c.sigma_label,
                "sigma_yu": c.sigma_yu,
                "epoch": c.epoch,
                "side_split": c.side_split,
                "q_me_yu": c.q_me_yu,
                "share": round(c.share, 9),
                "r_share_per_epoch_pendle": round(c.r_share_per_epoch_pendle, 6),
                "r_share_per_year_pendle": round(c.r_share_per_year_pendle, 6),
                "r_apr_usd_fraction": round(c.r_apr_usd_fraction, 6),
            }
            for c in cells
        ],
        low_apr=round(low, 6),
        mid_apr=round(mid, 6),
        high_apr=round(high, 6),
    )
    return out


# ── Sqlite + YAML readers (boundaries — not covered by smoke test) ─────────


def _read_e_liq_and_splits(
    sqlite_path: Path, market: str, derivation_date_utc: str
) -> tuple[float, float, float]:
    """Return (e_liq_per_epoch_pendle, side_split_prior, side_split_current).

    Reads operator rows from `state.market_reward_calibration` ordered by
    `calibrated_at_utc` DESC. When the table contains 2+ rows, the latest is
    treated as the current-epoch reading and the prior row as the prior-epoch
    reading (Phase 05.2 Bug #6 schema). When only one row exists, the same
    side_split is returned for both epochs and the caller should override
    `--side-split-prior` if a different prior-epoch value is needed.
    """
    if not sqlite_path.exists():
        raise FileNotFoundError(f"sqlite_path does not exist: {sqlite_path}")
    conn = sqlite3.connect(str(sqlite_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT calibrated_at_utc, e_liq_per_epoch_pendle, long_side_split, short_side_split "
            "FROM market_reward_calibration "
            "WHERE market_id = ? OR market_id LIKE ? "
            "ORDER BY calibrated_at_utc DESC",
            (market, f"%{market}%"),
        )
        rows = cur.fetchall()
        if len(rows) >= 2:
            current = rows[0]
            prior = rows[1]
            e_liq = float(current[1])
            return (e_liq, float(prior[2]), float(current[2]))
        if len(rows) == 1:
            current = rows[0]
            return (float(current[1]), float(current[2]), float(current[2]))
        raise RuntimeError(
            f"no market_reward_calibration rows for market={market!r}; "
            "operator must run reward_model calibrate CLI first"
        )
    finally:
        conn.close()


def _read_yaml_inputs(config_path: Path, market: str) -> dict[str, float]:
    """Return {collateral_usd, pendle_price_usd, q_max_yu, margin_per_yu_usd}."""
    cfg = yaml.safe_load(config_path.read_text())
    sizer = cfg["sizer"]
    pricing = cfg["pricing"]

    margin_per_yu_usd = float(sizer["margin_per_yu_usd"])
    for m in cfg.get("markets", []):
        if m["market_id"] == market and "margin_per_yu_usd" in m:
            margin_per_yu_usd = float(m["margin_per_yu_usd"])
            break

    collateral_usd = float(sizer["collateral_usd"])
    safety_margin = float(sizer["q_max_safety_margin"])
    q_max_yu = collateral_usd * safety_margin / margin_per_yu_usd

    return {
        "collateral_usd": collateral_usd,
        "pendle_price_usd": float(pricing["pendle_price_usd"]),
        "q_max_yu": q_max_yu,
        "margin_per_yu_usd": margin_per_yu_usd,
    }


def _select_sigma_anchors(side: str, sigma_source: str) -> dict[str, float]:
    """Return the sigma anchor dict for the requested side + source."""
    if sigma_source not in ("dapp", "parquet", "both"):
        raise ValueError(f"unknown sigma_source={sigma_source!r}")
    base = _DAPP_SIGMA_ANCHORS_LONG if side == "long" else _DAPP_SIGMA_ANCHORS_SHORT
    if sigma_source == "dapp":
        return dict(base)
    if sigma_source == "parquet":
        # Parquet readings are added by `_read_parquet_sigma`; we still seed with dapp anchors
        # so the band always brackets the badge anchor (for cross-check) — but the parquet
        # values dominate when present.
        return dict(base)
    # both
    return dict(base)


def _read_parquet_sigma(
    parquet_root: Path, market: str, side: str
) -> dict[str, float]:
    """Read 3 snapshots (start, mid, end) of order_book_raw and sum sz_float in CLO range.

    Returns {parquet_start, parquet_mid, parquet_end} sigma_yu values.

    Note: this is an OPTIONAL reading. The dapp-anchor values are the primary
    band-brackets per [[dapp-apr-reconciliation-2026-04-30]]. Parquet values
    serve as corroborating evidence for the realized in-window sigma.
    """
    import polars as pl  # type: ignore[import-not-found]

    market_dirs = sorted(
        (parquet_root / "order_book_raw").glob(f"market_id=*{market}")
    )
    if not market_dirs:
        raise FileNotFoundError(
            f"no order_book_raw partitions match market={market!r} under {parquet_root}"
        )
    market_dir = market_dirs[-1]  # highest numeric-prefix variant
    snapshot_dirs = sorted(market_dir.glob("snapshot_ts=*"))
    if len(snapshot_dirs) < 3:
        raise RuntimeError(
            f"need ≥3 snapshots for start/mid/end; found {len(snapshot_dirs)} in {market_dir}"
        )
    picks = [
        snapshot_dirs[0],
        snapshot_dirs[len(snapshot_dirs) // 2],
        snapshot_dirs[-1],
    ]
    out: dict[str, float] = {}
    for label, snap_dir in zip(("parquet_start", "parquet_mid", "parquet_end"), picks):
        files = list(snap_dir.glob("*.parquet"))
        if not files:
            continue
        df = pl.read_parquet(str(files[0])).filter(pl.col("side") == side)
        # Per [[dapp-apr-reconciliation-2026-04-30]], we use the cumulative-in-CLO-range
        # sum as the "raw_orderbook_in_range" reference — but the CLO range is in
        # fIndex-tick units that vary per snapshot. As a coarse proxy, use the sum of
        # sz_float across all rows in the snapshot — which is the broadest reading
        # equivalent to the dapp's "While Active/day" denominator.
        out[label] = float(df["sz_float"].sum())
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market", required=True)
    p.add_argument("--side", required=True, choices=("long", "short"))
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--epoch", default="both", choices=("prior", "current", "both"))
    p.add_argument("--sigma-source", default="dapp", choices=("dapp", "parquet", "both"))
    p.add_argument("--out-json", required=True, type=Path)
    p.add_argument("--sqlite-path", default=Path("state/state.sqlite"), type=Path)
    p.add_argument("--parquet-root", default=Path("data/parquet"), type=Path)
    p.add_argument(
        "--derivation-date-utc",
        default="2026-04-30",
        help="UTC date stamp for the band (no time.time() — chain_ts/data only).",
    )
    p.add_argument(
        "--override-e-liq-per-epoch",
        type=float,
        default=None,
        help="Override e_liq_per_epoch_pendle (otherwise read from market_reward_calibration).",
    )
    p.add_argument(
        "--override-long-split-prior",
        type=float,
        default=None,
        help="Override prior-epoch long_side_split (e.g. 0.327 from W0 evidence).",
    )
    p.add_argument(
        "--override-long-split-current",
        type=float,
        default=None,
        help="Override current-epoch long_side_split (e.g. 0.760 from t+11.5h dapp).",
    )
    args = p.parse_args(argv)

    yaml_inputs = _read_yaml_inputs(args.config, args.market)

    try:
        e_liq, long_split_prior, long_split_current = _read_e_liq_and_splits(
            args.sqlite_path, args.market, args.derivation_date_utc
        )
    except (FileNotFoundError, RuntimeError, sqlite3.OperationalError) as exc:
        if args.override_e_liq_per_epoch is None:
            raise RuntimeError(
                f"sqlite read failed ({exc}); supply --override-e-liq-per-epoch + "
                "--override-long-split-{prior,current} to bypass."
            ) from exc
        e_liq = args.override_e_liq_per_epoch
        long_split_prior = 0.5
        long_split_current = 0.5

    if args.override_e_liq_per_epoch is not None:
        e_liq = args.override_e_liq_per_epoch
    if args.override_long_split_prior is not None:
        long_split_prior = args.override_long_split_prior
    if args.override_long_split_current is not None:
        long_split_current = args.override_long_split_current

    side_split_prior = long_split_prior if args.side == "long" else (1.0 - long_split_prior)
    side_split_current = long_split_current if args.side == "long" else (1.0 - long_split_current)

    sigma_anchors = _select_sigma_anchors(args.side, args.sigma_source)
    if args.sigma_source in ("parquet", "both"):
        parquet_sigmas = _read_parquet_sigma(args.parquet_root, args.market, args.side)
        sigma_anchors.update(parquet_sigmas)

    q_max = yaml_inputs["q_max_yu"]
    q_me_grid = (q_max * 0.8, q_max, q_max * 1.2)

    inputs = BandInputs(
        market=args.market,
        side=args.side,
        epoch=args.epoch,
        sigma_yu_anchors=sigma_anchors,
        side_split_prior=side_split_prior,
        side_split_current=side_split_current,
        q_max_yu=q_max,
        q_me_grid_yu=q_me_grid,
        e_liq_per_epoch_pendle=e_liq,
        pendle_price_usd=yaml_inputs["pendle_price_usd"],
        collateral_usd=yaml_inputs["collateral_usd"],
        sigma_source=args.sigma_source,
    )

    out = derive_band(inputs, derivation_date_utc=args.derivation_date_utc)

    out.notes = [
        f"Formula: share = q_me / (sigma + q_me) × side_split × e_liq_per_epoch / collateral × 52 × pendle_price_usd",
        f"Source: [[pendle-lo-reward-formula-verified]] — Status: Current — PARTIAL (closed-source share calc)",
        f"Caveat: dapp-anchor sigmas span [{min(sigma_anchors.values()):.0f}, {max(sigma_anchors.values()):.0f}] YU; reflects unknown server-side denominator definition",
        f"q_max_yu = {q_max:.4f} (collateral=${yaml_inputs['collateral_usd']} × safety={yaml_inputs['margin_per_yu_usd']:.2f} margin/YU)",
        f"Plan 01 T7 verdict classification: PASS if r_apr_realized ∈ [low_apr × 0.5, high_apr × 1.5]; FLAG outside",
    ]

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out.__dict__, indent=2, default=str) + "\n")
    print(f"[band] wrote {args.out_json}")
    print(f"[band] low_apr={out.low_apr:.4f}  mid_apr={out.mid_apr:.4f}  high_apr={out.high_apr:.4f}")
    print(f"[band] cells={len(out.cells)}, sigmas={list(sigma_anchors.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
