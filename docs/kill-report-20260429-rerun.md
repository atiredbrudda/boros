# Phase 5.1 Ship-Gate: Re-Run FAIL Verdict (Corrected Inputs)

**Timestamp (UTC):** 2026-04-29T22:07:19.190687+00:00
**Git SHA:** 7244986216893a85d6df4108c6b57ef9374122fb
**Run ID:** 01KQDMC1DC3JW07VG2VMKKXM6T
**Parent Run ID:** 01KQB9CPQAQS31P2ZSY14DHYH6 (original FAIL run — stale inputs)
**Decision:** HALT CONTINUES — Phase 5.1 ship-gate re-run FAIL. Strategy yield below threshold even with corrected inputs.

## Context

This re-run corrects two stale inputs identified in the original FAIL run (`01KQB9CPQAQS31P2ZSY14DHYH6`, 2026-04-29T00:17 UTC):

1. `pricing.pendle_price_usd` corrected from 7.0 to 1.35 (operator-supplied real price)
2. `loss_model/replay.py:_REPLAY_SQL` column names corrected (`marketId`→`market_id`, `size`→`size_float`) + `_parquet_market_id()` helper added

A third fix was also applied: `loss_model/replay.py` used `.pl()` (DuckDB polars bridge) which requires pyarrow — not in project deps. Fixed to use `.fetchall()` + manual polars DataFrame construction. This is an environment fix, not a strategy change.

See [[ship-gate-verdict-20260429-stale-inputs]] for the pre-run analysis.

## Verdict Summary

| metric | value |
|--------|-------|
| p5_annualized_pnl (5th-pct block-bootstrap) | **0.0244** (2.44% APR) |
| threshold (alt_yield + all_fees) | **0.0600** (6.00% APR) |
| delta | **−0.0356** (−3.56 ppt) |
| passed | **false** |
| n_resamples | 2000 |
| block_seconds | 86400 (1-day blocks) |
| RNG seed | 283166975440376026 |
| n_fills | 0 |
| fragile_knobs | 0 |

## Comparison to Original Run

| metric | original (stale inputs) | re-run (corrected inputs) | delta |
|--------|------------------------|--------------------------|-------|
| p5_annualized_pnl | 0.49% APR | 2.44% APR | +1.95 ppt |
| gap to threshold | −5.51 ppt | −3.56 ppt | +1.95 ppt |
| shortfall attribution | 82% stale-pendle-price + 18% other | residual gap | — |

The corrected PENDLE price lifted p5 by ~4.98× (predicted: ~4.4× from stale-inputs analysis). The loss model fix contributed marginally — the long-side grid is now `fit_status=ok` (12 fills, 1 cell) vs `degraded` before, but outer-edge placements map to the grid's sparsest cells so the improvement in `expected_loss` accuracy had limited EV impact.

## Per-Market R_apr

Market tested: `BINANCE-ETHUSDT-25SEP2026` (highest-conviction shortlist market per [[markets-pre-filter-2026-04-26]] + [[phase-05-1-economics-gate-verdict]])

| market_id | side | e_liq_per_epoch_pendle | side_split | backtest_p5_apr | threshold | delta | halt_reason |
|-----------|------|------------------------|------------|-----------------|-----------|-------|-------------|
| BINANCE-ETHUSDT-25SEP2026 | long | 309.98 | 0.784 | 0.0244 | 0.0600 | −0.0356 | p5_below_threshold |

## Threshold Components

| component | value |
|-----------|-------|
| `screener.alt_yield` | 0.0500 |
| `backtest.all_fees_threshold` | 0.0100 |
| **Total** | **0.0600** |

## Loss Model Status (Re-Run)

| market_id | side | fit_status | n_fills | n_cells | impact |
|-----------|------|------------|---------|---------|--------|
| BINANCE-ETHUSDT-25SEP2026 | long | **ok** | 12 | 1 | Real KNN grid; outer-edge depth cell sparse → coarse fallback still dominant |
| BINANCE-ETHUSDT-25SEP2026 | short | degraded | 2 | 1 | Only 2 short-side fills; sparse grid |

232 fills had no matching close within 60s latency budget (sparse market, slow close).

## Remaining Engine-Completeness Caveat

**Sparse-event tick under-counting (unfixed):**
The backtest engine processes one decision per trade event. BINANCE-ETHUSDT-25SEP2026 averages ~2-4 trades/day (237 events over 26 days). Between events, the 1 Hz reward-accrual clock does not fire. The live 1 Hz loop accrues reward continuously. This structural gap means the engine under-counts reward proportional to inter-event gaps (typically 3-12 hours). Correcting this would require synthesizing 1 Hz synthetic ticks between events — not in v0.5 engine.

**Estimated remaining impact:** If sparse-tick under-counting accounts for a factor of ~2-3× on a market with 3 trades/day (86400s/day ÷ ~30,000s between events = ~2.9 real decisions per event that accrue reward), correcting it might bring p5 to ~5-7% APR. This is the primary remaining caveat before a Phase 6 re-run would be warranted.

## Perturbation Grid (BACK-08)

- Total numeric leaves perturbed: **109**
- Fragile knobs (sign-flip on ±20%): **0**
- Interpretation: zero fragile knobs — p5 stable across all parameter directions; shortfall is structural, not tuning-sensitive.

## What Changed vs Original Input-Stale Run

| fix | predicted effect | actual effect |
|-----|-----------------|---------------|
| `pendle_price_usd` 7.0→1.35 | ~4.4× reward lift (cap sub→cap_binding regime shift) | ~4.98× observed |
| loss_model SQL fix (246 rows vs 0) | partial; outer-edge cells still sparse | marginal (grid ok but most lookups coarse-bound) |
| `.pl()` → `.fetchall()` polars | environment fix, strategy-neutral | confirms 246 fill rows returned |

## Reproducibility

```bash
uv run --directory python python -m boros_brain.backtest \
  --config /Users/macbookair/boros/strategy/v0.5-phase05.1-shortlist.yaml \
  run --market BINANCE-ETHUSDT-25SEP2026 --side long
```

Run ID `01KQDMC1DC3JW07VG2VMKKXM6T` (ULID-seeded RNG, git SHA 7244986).

## Artifacts

- Verdict JSON: `data/parquet/backtest_results/run_id=01KQDMC1DC3JW07VG2VMKKXM6T/ship_gate_verdict.json`
- Ship-gate report: `var/backtest/01KQDMC1DC3JW07VG2VMKKXM6T/ship-gate-report.md`
- Manifest sidecar: `var/backtest/01KQDMC1DC3JW07VG2VMKKXM6T/01KQDMC1DC3JW07VG2VMKKXM6T.manifest.json`
- Log: `logs/2026-04-29/01KQDMC1DC3JW07VG2VMKKXM6T.backtest-cli.log.jsonl`

## Follow-Up Findings (Next Decision Point)

1. **Sparse-event tick synthesis** — largest remaining engine gap. Adding 1 Hz synthetic ticks between trade events would require `_sim_duration_s`-style interpolation in the replay loop, driven by real blockTimestamp spacing. This is the most likely path to a PASS verdict if the strategy is genuinely viable.
2. **Unit-mismatch in EV metric** — `daily_pnl` is in PENDLE units vs `alt_yield=0.05` which is a USD APR fraction. The comparison is PENDLE-APR-ish. Resolving this requires `pendle_price_usd`-weighted USD conversion at the daily PnL aggregation step (Phase 3 deep issue per [[unit-consistency-pendle-units-v05]]).
3. **Loss grid sparsity** — 12 long-side fills is not enough for a meaningful KNN grid at outer-edge (depth≈100 ticks). Fix requires either a longer window (>90 days) or a coarser bucketing in `depth_bucket_edges`.

Wiki: [[ship-gate-verdict-20260429-rerun]]
