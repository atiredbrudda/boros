/**
 * Boros hands entrypoint.
 *
 * Boot contract (matches the Python MANIFEST-FIRST protocol on the brain side):
 *   1. Read BOROS_RUN_ID + BOROS_LOGS_DIR from env (brain spawns hands with these set).
 *   2. configureHandsLogger opens the log file.
 *   3. Wrap the coroutine in ctxStore.run so `run_id` propagates via AsyncLocalStorage.
 *   4. (Plan 01-03 Task 2) wire CmdListener + EventPublisher + heartbeat.
 *   5. Await SIGTERM / SIGINT.
 *
 * // ZMQ bus wired by plan 01-03 Task 2 (INFRA-05).
 * // Socket.IO listener wired by Phase 6 (EXEC / WS).
 */

import { configureHandsLogger, ctxStore } from "./logger.js";

export async function main(): Promise<number> {
	const run_id = process.env.BOROS_RUN_ID ?? "<unassigned>";
	const logsDir = process.env.BOROS_LOGS_DIR ?? "logs";
	const logger = configureHandsLogger(run_id, logsDir);

	return new Promise<number>((resolve) => {
		ctxStore.run({ run_id, tier: "hands" }, () => {
			logger.info({ event: "hands_booted" });

			const shutdown = (): void => {
				logger.info({ event: "hands_shutdown" });
				resolve(0);
			};
			process.once("SIGTERM", shutdown);
			process.once("SIGINT", shutdown);
		});
	});
}

// Only auto-run when executed directly (tsx src/boros_hands/main.ts), not when imported.
if (import.meta.url === `file://${process.argv[1]}`) {
	main().then((code) => {
		process.exit(code);
	});
}
