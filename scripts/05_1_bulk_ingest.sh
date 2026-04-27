#!/usr/bin/env bash
# Phase 05.1 — bulk ingest orchestrator
#
# Iterates data/ndjson tree and dispatches per-(kind, src, market) ingester
# subprocess at -P 4 concurrency via uv run --directory python.
#
# Surfaces ALL failures to logs/05.1-bulk-ingest-failed.log.
# DO NOT swallow AMMConservationError or IngesterSchemaViolation — both must surface.
#
# Usage:
#   bash scripts/05_1_bulk_ingest.sh
#
# Exit codes:
#   0 — all ingest jobs succeeded
#   1 — one or more ingest jobs failed (see logs/05.1-bulk-ingest-failed.log)

set -uo pipefail

BOROS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BOROS_ROOT"

INGEST_LOG="$BOROS_ROOT/logs/05.1-bulk-ingest.log"
FAILED_LOG="$BOROS_ROOT/logs/05.1-bulk-ingest-failed.log"
DRIVER_LOG="$BOROS_ROOT/logs/05.1-bulk-ingest-driver.log"

mkdir -p "$BOROS_ROOT/logs" "$BOROS_ROOT/data/parquet"

: > "$INGEST_LOG"
: > "$FAILED_LOG"
: > "$DRIVER_LOG"

log_driver() { echo "$@" | tee -a "$DRIVER_LOG"; }

log_driver "=== Phase 05.1 Bulk Ingest ==="
log_driver "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log_driver "Root: $BOROS_ROOT"

# ── Ingest helper function ────────────────────────────────────────────────────
# Usage: run_ingest <kind> <src> [extra_args...]
run_ingest() {
    local kind="$1"; local src="$2"; shift 2

    {
        echo "=== $kind $src ==="
        if uv run --directory "$BOROS_ROOT/python" python -m boros_brain.data.ingester.cli \
             --kind "$kind" \
             --src "$src" \
             --out "$BOROS_ROOT/data/parquet" \
             --config "$BOROS_ROOT/strategy/v0.5-default.yaml" \
             "$@" 2>&1; then
            echo "OK $kind $src"
        else
            local exit_code=$?
            echo "FAIL(exit=$exit_code) $kind $src" >> "$FAILED_LOG"
        fi
    } >> "$INGEST_LOG"
}

# ── Collect and dispatch jobs in parallel using background processes ──────────
# We use a semaphore-like approach: maintain at most 4 concurrent bg processes.

PIDS=()
CONCURRENCY=4

wait_for_slot() {
    while [ "${#PIDS[@]}" -ge "$CONCURRENCY" ]; do
        local new_pids=()
        for pid in "${PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                new_pids+=("$pid")
            fi
        done
        PIDS=("${new_pids[@]:-}")
        if [ "${#PIDS[@]}" -ge "$CONCURRENCY" ]; then
            sleep 0.1
        fi
    done
}

TOTAL=0

# market_trades
log_driver "Enumerating market_trades..."
for f in "$BOROS_ROOT"/data/ndjson/market-trades/*/*.ndjson; do
    [ -f "$f" ] || continue
    market=$(basename "$(dirname "$f")")
    wait_for_slot
    run_ingest market_trades "$f" --market-id "$market" &
    PIDS+=($!)
    TOTAL=$(( TOTAL + 1 ))
done

# order_book_raw
log_driver "Enumerating order_book_raw..."
for f in "$BOROS_ROOT"/data/ndjson/order-book/*/raw/*.ndjson; do
    [ -f "$f" ] || continue
    market=$(basename "$(dirname "$(dirname "$f")")")
    wait_for_slot
    run_ingest order_book_raw "$f" --market-id "$market" &
    PIDS+=($!)
    TOTAL=$(( TOTAL + 1 ))
done

# order_book_combined
log_driver "Enumerating order_book_combined..."
for f in "$BOROS_ROOT"/data/ndjson/order-book/*/combined_*/*.ndjson; do
    [ -f "$f" ] || continue
    tickdir=$(basename "$(dirname "$f")")
    tick=${tickdir#combined_}
    market=$(basename "$(dirname "$(dirname "$f")")")
    wait_for_slot
    run_ingest order_book_combined "$f" --market-id "$market" --tick-size "$tick" &
    PIDS+=($!)
    TOTAL=$(( TOTAL + 1 ))
done

# underlying_apr
log_driver "Enumerating underlying_apr..."
for f in "$BOROS_ROOT"/data/ndjson/underlying-apr/*.ndjson; do
    [ -f "$f" ] || continue
    basename_no_ext=$(basename "$f" .ndjson)
    exchange="${basename_no_ext%%-*}"
    wait_for_slot
    run_ingest underlying_apr "$f" --exchange "$exchange" &
    PIDS+=($!)
    TOTAL=$(( TOTAL + 1 ))
done

# settlement_md
log_driver "Enumerating settlement_md..."
for f in "$BOROS_ROOT"/data/ndjson/settlement/*/*.ndjson; do
    [ -f "$f" ] || continue
    market=$(basename "$(dirname "$f")")
    wait_for_slot
    run_ingest settlement_md "$f" --market-id "$market" &
    PIDS+=($!)
    TOTAL=$(( TOTAL + 1 ))
done

# Wait for all remaining jobs
log_driver "Waiting for $TOTAL jobs to complete..."
wait

# ── Result summary ────────────────────────────────────────────────────────────

log_driver ""
log_driver "=== Ingest Complete ==="
log_driver "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log_driver "Total jobs dispatched: $TOTAL"

FAIL_COUNT=$(wc -l < "$FAILED_LOG" | tr -d ' ')
OK_COUNT=$(grep -c '^OK ' "$INGEST_LOG" 2>/dev/null || echo 0)
log_driver "Succeeded: $OK_COUNT / $TOTAL"

MARKET_PARTITIONS=$(find "$BOROS_ROOT/data/parquet" -type d -name 'market_id=*' 2>/dev/null | wc -l | tr -d ' ')
log_driver "Parquet market_id= partitions: $MARKET_PARTITIONS"

if [ "$FAIL_COUNT" -gt 0 ]; then
    log_driver ""
    log_driver "FAILURES ($FAIL_COUNT):"
    cat "$FAILED_LOG" | tee -a "$DRIVER_LOG"
    log_driver "See $FAILED_LOG for full failure list."
    log_driver "File a wiki page for each AMM/schema violation per plan."
    exit 1
fi

log_driver "All ingests OK."
exit 0
