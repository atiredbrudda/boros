"""Deterministic generator for loss_grid_synthetic_fills.parquet. Seed = 42.

SSoT: this script. Committed parquet is the artifact consumed by
test_loss_model_replay.py and test_loss_model_fit_and_expected_loss.py.

Design:
- 7 depth buckets × 6 tau buckets × 2 sides; ~10 fills per cell at interior cells,
  5 fills at edge cells. Total: roughly 720-840 rows depending on edge sparsity.
- pnl_pendle drawn from N(-(depth_bucket_idx * 0.01), 0.005) so deeper cells have
  larger expected losses (sign convention: negative = loss).
- Fields cover the PerFillPnL dataclass shape so callers can build PerFillPnL
  rows directly from the fixture without re-running DuckDB replay.

Regenerate with:
    cd /Users/macbookair/boros && \
        uv --directory python run python python/tests/fixtures/_generate_loss_grid_fixtures.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

FIXTURE_DIR = Path(__file__).parent
MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def generate_synthetic_fills(out_path: Path, rng: np.random.Generator) -> None:
    """Write a synthetic per-fill parquet covering the (depth, tau) grid.

    Each (depth_bucket_idx, tau_bucket_idx, side) cell gets exactly 10 fills
    when depth_idx < 6 and tau_idx < 5; edge cells (depth_idx == 6 or tau_idx == 5)
    get 5 fills. This guarantees min_samples_per_cell = 5 is satisfied everywhere
    at the default config, and 10 is comfortably exceeded in the interior so the
    fit_status='ok' path is exercised.
    """
    rows: list[dict] = []
    base_ts = 1_700_000_000  # 2023-11-14T22:13:20Z, anchor outside any real chain ts
    for depth_idx in range(7):
        for tau_idx in range(6):
            for side in ("long", "short"):
                # Edge cells (terminal depth or tau bucket): n=5; interior n=10
                n_fills = 5 if (depth_idx == 6 or tau_idx == 5) else 10
                for _ in range(n_fills):
                    block_ts = base_ts + len(rows) * 60
                    fill_rate = 0.10 + depth_idx * 0.001
                    close_rate = fill_rate + float(rng.normal(0, 0.001))
                    pnl = float(rng.normal(-(depth_idx * 0.01), 0.005))
                    rows.append(
                        {
                            "market_id": MARKET_ID,
                            "side": side,
                            "fill_event_index": len(rows) * 1000,
                            "fill_block_ts": block_ts,
                            "fill_rate": fill_rate,
                            "fill_size_float": 0.5,
                            # Land squarely in bucket depth_idx for default depth_bucket_edges.
                            # Edges = [0, 1, 2, 4, 8, 16, 32, 10000].
                            "depth_from_mark_ticks": int(
                                [0, 1, 2, 4, 8, 16, 32][depth_idx]
                            )
                            + (0 if depth_idx == 0 else 0),
                            # Land in bucket tau_idx for tau_bucket_edges_days
                            # = [0, 7, 14, 30, 60, 90, 180, 10000].
                            "tau_days": float(
                                [3.0, 10.0, 20.0, 45.0, 75.0, 120.0, 200.0][tau_idx]
                            ),
                            "close_rate": close_rate,
                            "close_block_ts": block_ts + 30,
                            "close_latency_s": 30.0,
                            "pnl_pendle": pnl,
                            "fee_taker_pendle": 0.0001,
                            "fee_settlement_pendle": 0.00005,
                            "fee_entrance_amortized_pendle": 0.00001,
                            "fee_gas_pendle": 0.000001,
                        }
                    )
    pl.DataFrame(rows).write_parquet(out_path)
    print(f"wrote {out_path} ({len(rows)} rows, seed=42)")


def main() -> None:
    rng = np.random.default_rng(42)
    generate_synthetic_fills(FIXTURE_DIR / "loss_grid_synthetic_fills.parquet", rng)
    print("regenerated")


if __name__ == "__main__":
    main()
