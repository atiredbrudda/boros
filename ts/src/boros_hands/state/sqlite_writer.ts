/**
 * INFRA-03 — hands-side SQLite writer (production owner of `open_orders` + `tx_receipts`).
 *
 * PROTO-02 single-writer discipline: this file is the ONLY place in the TS codebase
 * containing write SQL for `open_orders` or `tx_receipts`. `scripts/sqlite_writer_lint.py`
 * grep-enforces this at commit time.
 *
 * The hot fill → cancel path reads/writes `open_orders` here without a ZMQ hop
 * to preserve the 2–5s end-to-end cancel latency budget (see CLAUDE.md §Stack).
 */

import Database from 'better-sqlite3';

export type Side = 'long' | 'short';
export type OpenOrderStatus =
  | 'filling'
  | 'cancelled'
  | 'fully_filled'
  | 'expired'
  | 'purged';
export type TxStatus = 'pending' | 'confirmed' | 'reverted' | 'dropped';

export interface OpenOrderRow {
  order_id: string;
  market_id: string;
  side: Side;
  depth_ticks: number;
  size_wei: string; // 256-bit wei, kept as TEXT
  rate: number;
  status: OpenOrderStatus;
  placed_at_ts: number;
  run_id: string;
}

export interface TxReceiptRow {
  tx_hash: string;
  run_id: string;
  submitted_at_ts: number;
  confirmed_at_ts: number | null;
  status: TxStatus;
  gas_used: number | null;
  intent: string; // 'place' | 'cancel' | 'close' | 'claim' | 'approve' | ...
  related_order_id: string | null;
}

/**
 * Open a WAL-mode better-sqlite3 connection with FKs on. Mirrors the Python-side
 * `open_connection()` contract. The caller owns closing the connection.
 *
 * File permissions are NOT adjusted here — the Python-side `open_connection()`
 * clamps 0o600 on first-open; subsequent opens (Python or TS) inherit the mode.
 * If the TS-side opens a brand-new DB before Python does, chmod 600 is deferred
 * until Python first opens it — acceptable because the production boot order is
 * brain-first (alembic upgrade runs before hands starts).
 */
export function openHandsDb(path: string): Database.Database {
  const db = new Database(path);
  db.pragma('journal_mode = WAL');
  db.pragma('synchronous = NORMAL');
  db.pragma('foreign_keys = ON');
  return db;
}

/**
 * Upsert an open-order row. On place, inserts new; on subsequent status transitions
 * (`filling` → `cancelled` / `fully_filled` / `expired` / `purged`), updates the
 * existing row's status in place.
 */
export function upsertOpenOrder(db: Database.Database, row: OpenOrderRow): void {
  db.prepare(
    `INSERT INTO open_orders
       (order_id, market_id, side, depth_ticks, size_wei, rate, status, placed_at_ts, run_id)
     VALUES (@order_id, @market_id, @side, @depth_ticks, @size_wei, @rate, @status, @placed_at_ts, @run_id)
     ON CONFLICT(order_id) DO UPDATE SET status = excluded.status`,
  ).run(row);
}

/**
 * Update an existing open_order's status (cancel-confirmation / fill-confirmation flows).
 */
export function updateOpenOrderStatus(
  db: Database.Database,
  orderId: string,
  status: OpenOrderStatus,
): void {
  db.prepare('UPDATE open_orders SET status = @status WHERE order_id = @order_id').run({
    order_id: orderId,
    status,
  });
}

/**
 * Insert a tx_receipts row. Send Txs Bot submit → one row with status='pending';
 * downstream confirmation flow updates status + confirmed_at_ts + gas_used.
 */
export function insertTxReceipt(db: Database.Database, row: TxReceiptRow): void {
  db.prepare(
    `INSERT INTO tx_receipts
       (tx_hash, run_id, submitted_at_ts, confirmed_at_ts, status, gas_used, intent, related_order_id)
     VALUES (@tx_hash, @run_id, @submitted_at_ts, @confirmed_at_ts, @status, @gas_used, @intent, @related_order_id)`,
  ).run(row);
}

/**
 * Update a pending tx_receipts row with confirmation metadata.
 */
export function confirmTxReceipt(
  db: Database.Database,
  args: {
    tx_hash: string;
    confirmed_at_ts: number;
    status: Exclude<TxStatus, 'pending'>;
    gas_used: number | null;
  },
): void {
  db.prepare(
    `UPDATE tx_receipts
       SET confirmed_at_ts = @confirmed_at_ts,
           status          = @status,
           gas_used        = @gas_used
     WHERE tx_hash = @tx_hash`,
  ).run(args);
}
