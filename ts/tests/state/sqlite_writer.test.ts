/**
 * INFRA-03 — hands-side better-sqlite3 writer round-trip tests.
 *
 * Runs the Python alembic migration via `execSync` against a tmp DB, then
 * exercises `openHandsDb` + `upsertOpenOrder` + `insertTxReceipt` in WAL mode
 * and reads the rows back via raw prepared statements.
 */

import { execSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
	insertTxReceipt,
	openHandsDb,
	upsertOpenOrder,
} from "../../src/boros_hands/state/sqlite_writer.js";

// Repo root = ts/tests/state → ts/tests → ts → repo
const REPO_ROOT = resolve(__dirname, "../../..");
const PYTHON_DIR = resolve(REPO_ROOT, "python");
const APPLY_MIGRATION = resolve(
	REPO_ROOT,
	"scripts/apply_alembic_migration.py",
);

describe("hands sqlite_writer — WAL round-trips", () => {
	let workdir: string;
	let dbPath: string;

	beforeEach(() => {
		workdir = mkdtempSync(join(tmpdir(), "boros-hands-sqlite-"));
		dbPath = join(workdir, "state.sqlite");
		// Apply the brain's alembic migration to the tmp DB via the helper script —
		// driving Alembic programmatically avoids the -x / ini-override CLI limitation.
		execSync(`uv run python ${APPLY_MIGRATION} sqlite:///${dbPath}`, {
			cwd: PYTHON_DIR,
			stdio: "pipe",
		});
	});

	afterEach(() => {
		rmSync(workdir, { recursive: true, force: true });
	});

	it("open_orders upsert round-trips in WAL mode", () => {
		const db = openHandsDb(dbPath);
		try {
			expect(db.pragma("journal_mode", { simple: true })).toBe("wal");
			expect(db.pragma("foreign_keys", { simple: true })).toBe(1);

			upsertOpenOrder(db, {
				order_id: "ord-1",
				market_id: "ETHUSDT-29MAY2026",
				side: "long",
				depth_ticks: 50,
				size_wei: "1000000000000000000",
				rate: 9400,
				status: "filling",
				placed_at_ts: 1_714_000_000,
				run_id: "run-abc",
			});

			const row = db
				.prepare(
					"SELECT order_id, status, side FROM open_orders WHERE order_id = ?",
				)
				.get("ord-1") as { order_id: string; status: string; side: string };
			expect(row).toEqual({
				order_id: "ord-1",
				status: "filling",
				side: "long",
			});

			// Upsert to cancelled must update status in place.
			upsertOpenOrder(db, {
				order_id: "ord-1",
				market_id: "ETHUSDT-29MAY2026",
				side: "long",
				depth_ticks: 50,
				size_wei: "1000000000000000000",
				rate: 9400,
				status: "cancelled",
				placed_at_ts: 1_714_000_000,
				run_id: "run-abc",
			});
			const updated = db
				.prepare("SELECT status FROM open_orders WHERE order_id = ?")
				.get("ord-1") as { status: string };
			expect(updated.status).toBe("cancelled");
		} finally {
			db.close();
		}
	});

	it("tx_receipts insert round-trips", () => {
		const db = openHandsDb(dbPath);
		try {
			insertTxReceipt(db, {
				tx_hash: "0xabc",
				run_id: "run-abc",
				submitted_at_ts: 1_714_000_000,
				confirmed_at_ts: null,
				status: "pending",
				gas_used: null,
				intent: "place",
				related_order_id: "ord-1",
			});
			const row = db
				.prepare(
					"SELECT tx_hash, intent, related_order_id, status FROM tx_receipts",
				)
				.get() as {
				tx_hash: string;
				intent: string;
				related_order_id: string;
				status: string;
			};
			expect(row).toEqual({
				tx_hash: "0xabc",
				intent: "place",
				related_order_id: "ord-1",
				status: "pending",
			});
		} finally {
			db.close();
		}
	});
});
