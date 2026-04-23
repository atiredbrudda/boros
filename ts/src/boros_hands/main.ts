/**
 * Boros hands entrypoint skeleton.
 *
 * Wave-0 shim: boots, prints a single line, awaits SIGTERM, exits 0.
 *
 * // ZMQ bus wired by plan 01-03 (INFRA-05).
 * // pino logger wired by plan 01-03 (INFRA-07).
 * // Socket.IO listener wired by Phase 6 (EXEC / WS).
 */

export async function main(): Promise<number> {
  const runId = process.env.BOROS_RUN_ID ?? '<unassigned>';
  // eslint-disable-next-line no-console
  console.log(`boros-hands booted run_id=${runId}`);

  return new Promise<number>((resolve) => {
    const shutdown = (): void => {
      // eslint-disable-next-line no-console
      console.log('boros-hands received SIGTERM — exiting');
      resolve(0);
    };
    process.once('SIGTERM', shutdown);
    process.once('SIGINT', shutdown);
  });
}

// Only auto-run when executed directly (tsx src/boros_hands/main.ts), not when imported.
if (import.meta.url === `file://${process.argv[1]}`) {
  main().then((code) => {
    process.exit(code);
  });
}
