"""Tests for scripts/audit_n_fills_against_edges.py (E4 audit, Phase 05.2 Wave 0).

Cases:
1. test_audit_n_fills_runs_on_real_data
   plot_apr_vs_edges returns stats dict with numeric keys; PNG file written > 1024 bytes.

2. test_audit_n_fills_writes_verdict_json
   main() returns 0; verdict JSON exists with all required keys; verdict_label is valid.

3. test_load_implied_apr_series_returns_sorted
   On a synthetic fixture parquet, load_implied_apr_series returns a sorted DataFrame
   with the expected columns [blockTimestamp, implied_apr_pct].
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_n_fills_against_edges.py"

# Load module from script path without installing it
spec = importlib.util.spec_from_file_location("audit_n_fills_against_edges", SCRIPT)
assert spec is not None and spec.loader is not None
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)  # type: ignore[union-attr]

load_implied_apr_series = _mod.load_implied_apr_series
plot_apr_vs_edges = _mod.plot_apr_vs_edges
main = _mod.main

PARQUET_ROOT = ROOT / "data" / "parquet"
BINDING_MARKET = "BINANCE-ETHUSDT-25SEP2026"

VERDICT_LABELS = {"real_no_fills", "sim_bug_under_counting", "inconclusive"}
REQUIRED_STAT_KEYS = {"n_crossings_lo", "n_crossings_hi", "max_apr_pct", "min_apr_pct", "mean_apr_pct"}
REQUIRED_VERDICT_KEYS = {
    "market_id",
    "n_crossings_lo",
    "n_crossings_hi",
    "max_apr_pct",
    "min_apr_pct",
    "mean_apr_pct",
    "verdict_label",
}


def _make_fixture_parquet(tmp_path: Path) -> Path:
    """Write a small synthetic parquet fixture matching the market_trades schema."""
    market_dir = tmp_path / "data" / "parquet" / "market_trades" / "market_id=101-BINANCE-ETHUSDT-25SEP2026"
    market_dir.mkdir(parents=True)
    base_ts = 1_700_000_000
    # 1000 rows; rate in [0.005, 0.015] → implied_apr_pct in [0.5, 1.5] (straddles both edges)
    import random

    random.seed(42)
    rows = [
        {
            "blockTimestamp": base_ts + i * 3600,
            "rate": 0.005 + (i % 100) * 0.0001,
            "market_id": "101-BINANCE-ETHUSDT-25SEP2026",
        }
        for i in range(1000)
    ]
    df = pl.DataFrame(rows)
    df.write_parquet(market_dir / "data.parquet")
    return tmp_path / "data" / "parquet"


def test_audit_n_fills_runs_on_real_data(tmp_path: Path) -> None:
    """plot_apr_vs_edges returns numeric stats; PNG written > 1024 bytes."""
    df = load_implied_apr_series(PARQUET_ROOT, BINDING_MARKET, days=26)
    out_png = tmp_path / "test.png"
    stats = plot_apr_vs_edges(df, edge_lo_pct=0.74, edge_hi_pct=1.26, out_png=out_png)

    assert set(stats.keys()) == REQUIRED_STAT_KEYS, f"Missing keys: {REQUIRED_STAT_KEYS - set(stats.keys())}"
    for key in REQUIRED_STAT_KEYS:
        assert isinstance(stats[key], int | float), f"{key} is not numeric: {stats[key]!r}"
    assert out_png.exists(), "PNG file was not created"
    assert out_png.stat().st_size > 1024, f"PNG too small: {out_png.stat().st_size} bytes"


def test_audit_n_fills_writes_verdict_json(tmp_path: Path) -> None:
    """main() exits 0; verdict JSON has all required keys; verdict_label is valid."""
    out_json = ROOT / "var" / "reports" / "n_fills_audit_verdict.json"
    exit_code = main(
        [
            "--market",
            BINDING_MARKET,
            "--days",
            "26",
            "--edge-lo-pct",
            "0.74",
            "--edge-hi-pct",
            "1.26",
        ]
    )
    assert exit_code == 0, f"main() returned non-zero: {exit_code}"
    assert out_json.exists(), f"Verdict JSON not found: {out_json}"
    verdict = json.loads(out_json.read_text())
    missing = REQUIRED_VERDICT_KEYS - set(verdict.keys())
    assert not missing, f"Verdict JSON missing keys: {missing}"
    assert (
        verdict["verdict_label"] in VERDICT_LABELS
    ), f"verdict_label {verdict['verdict_label']!r} not in {VERDICT_LABELS}"


def test_load_implied_apr_series_returns_sorted(tmp_path: Path) -> None:
    """On a synthetic parquet, load_implied_apr_series returns sorted [blockTimestamp, implied_apr_pct]."""
    fixture_root = _make_fixture_parquet(tmp_path)
    df = load_implied_apr_series(fixture_root, "BINANCE-ETHUSDT-25SEP2026", days=365)

    assert not df.is_empty(), "Expected non-empty DataFrame from synthetic fixture"
    assert list(df.columns) == ["blockTimestamp", "implied_apr_pct"], f"Unexpected columns: {df.columns}"
    assert df.schema["blockTimestamp"] == pl.Int64, f"blockTimestamp dtype: {df.schema['blockTimestamp']}"
    assert df.schema["implied_apr_pct"] == pl.Float64, f"implied_apr_pct dtype: {df.schema['implied_apr_pct']}"
    ts = df["blockTimestamp"].to_list()
    assert ts == sorted(ts), "DataFrame is not sorted by blockTimestamp"
