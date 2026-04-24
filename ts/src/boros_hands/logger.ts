/**
 * INFRA-07 — pino logger mirroring the Python structlog contract.
 *
 * Shared minimum record shape (same as python/src/boros_brain/logging/schema.py):
 *   ts, level, event, run_id, tier, logger, pid
 *
 * `run_id` propagates through async call graphs via `AsyncLocalStorage`; callers
 * wrap the work in `ctxStore.run({ run_id, tier }, async () => { ... })` and the
 * `mixin` on the pino instance pulls the active run_id into every record.
 *
 * Boot contract (matches Python MANIFEST-FIRST):
 *   1. hands reads BOROS_RUN_ID from env (set by brain / launchd plist).
 *   2. configureHandsLogger(run_id, logsDir) opens the log file.
 *   3. ctxStore.run({run_id, tier}, ...) wraps the main coroutine.
 */

import { AsyncLocalStorage } from "node:async_hooks";
import fs from "node:fs";
import path from "node:path";

import pino from "pino";

export interface HandsLogContext {
	run_id: string;
	tier: "brain" | "hands";
}

export const ctxStore = new AsyncLocalStorage<HandsLogContext>();

let _log: pino.Logger | null = null;

/**
 * Open `<logsDir>/<YYYY-MM-DD>/<run_id>.hands.log.jsonl` and configure a pino
 * instance whose output matches the structlog minimum record shape.
 *
 * Subsequent `configureHandsLogger` calls (same process) overwrite the prior
 * instance — intended only for tests that want a fresh destination per case.
 */
export function configureHandsLogger(
	run_id: string,
	logsDir: string,
): pino.Logger {
	const date = new Date().toISOString().slice(0, 10);
	const dir = path.join(logsDir, date);
	fs.mkdirSync(dir, { recursive: true });
	const dest = pino.destination({
		dest: path.join(dir, `${run_id}.hands.log.jsonl`),
		sync: true, // small, line-level writes — sync is fine for a local bot
	});
	_log = pino(
		{
			level: "info",
			// Structlog uses a top-level `ts` key (ISO 8601 UTC). Mirror exactly.
			timestamp: () => `,"ts":"${new Date().toISOString()}"`,
			formatters: {
				level: (label) => ({ level: label }),
				bindings: (b) => ({
					pid: b.pid,
					tier: "hands",
					// structlog uses `logger` as the logger name; pino calls it `name`.
					logger: (b as { name?: string }).name ?? "boros_hands",
				}),
			},
			mixin: () => {
				const ctx = ctxStore.getStore();
				return ctx
					? { run_id: ctx.run_id, tier: ctx.tier }
					: { run_id, tier: "hands" };
			},
		},
		dest,
	);
	return _log;
}

/** Get the currently-configured logger. Throws if `configureHandsLogger` was never called. */
export function log(): pino.Logger {
	if (!_log) {
		throw new Error("configureHandsLogger() must be called before log()");
	}
	return _log;
}
