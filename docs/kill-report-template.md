# Project Halt: Economics Kill-Switch Empty Shortlist

**Timestamp (UTC):** {timestamp_iso}
**Git SHA:** {git_sha}
**Run ID:** {run_id}
**Decision:** HALT -- no market passes DATA-09 economics gate.

## Per-Market Evaluation

| market_id | R_apr_on_collateral | alt_yield_used | fill_loss_used | threshold | delta | halt_reason |
|-----------|---------------------|----------------|----------------|-----------|-------|-------------|
{rows}

## Knobs Snapshot (RUN_MANIFEST config tree)

```json
{knob_tree_json}
```

## Halt Semantics

- `drop(market) iff R_apr_on_collateral < alt_yield + fill_loss_coarse_bound` -> threshold = {threshold:.4f}
- delta < 0 for EVERY shortlist candidate -> shortlist empty -> project halts.
- No downstream phase (2+) work is started until a market passes.

## Possible Remediations

1. Wait for new markets (DATA-10 daily re-screen will detect new-entrants; this report reruns).
2. Re-verify `alt_yield` against current Arbitrum stablecoin market (may have shifted).
3. Re-verify `fill_loss_coarse_bound` against current CLO-edge fill rates (A1 -- Phase 3 refines).
4. Escalate to PROJECT.md review: is the thesis still viable?

Filed to wiki: [[Economics kill-switch v0.5]]
