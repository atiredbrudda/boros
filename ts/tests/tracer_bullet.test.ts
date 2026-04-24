import { execSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { configureHandsLogger, ctxStore, log } from '../src/boros_hands/logger.js';
import { openHandsDb, upsertOpenOrder } from '../src/boros_hands/state/sqlite_writer.js';

const REPO_ROOT = resolve(__dirname, '../..');
const PYTHON_DIR = resolve(REPO_ROOT, 'python');
const APPLY_MIGRATION = resolve(REPO_ROOT, 'scripts/apply_alembic_migration.py');

describe('tracer bullet (wave 0 scaffold)', () => {
  let workdir: string;
  let dbPath: string;

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'boros-tracer-'));
    dbPath = join(workdir, 'state.sqlite');
    execSync(`uv run python ${APPLY_MIGRATION} sqlite:///${dbPath}`, {
      cwd: PYTHON_DIR,
      stdio: 'pipe',
    });
  });

  afterEach(() => {
    rmSync(workdir, { recursive: true, force: true });
  });

  it('pino JSON shape matches structlog contract', () => {
    // INFRA-07 un-skip: plan 01-03 Task 1 landed the pino logger + AsyncLocalStorage.
    const logsDir = join(workdir, 'logs');
    configureHandsLogger('TRACER_RUN', logsDir);
    ctxStore.run({ run_id: 'TRACER_RUN', tier: 'hands' }, () => {
      log().info({ event: 'tracer_event' });
    });
    const dateDirs = readdirSync(logsDir);
    const logPath = join(logsDir, dateDirs[0], 'TRACER_RUN.hands.log.jsonl');
    const firstLine = readFileSync(logPath, 'utf-8').split('\n').filter(Boolean)[0];
    const rec = JSON.parse(firstLine);
    for (const f of ['ts', 'level', 'event', 'run_id', 'tier', 'logger', 'pid']) {
      expect(rec).toHaveProperty(f);
    }
    expect(rec.run_id).toBe('TRACER_RUN');
    expect(rec.tier).toBe('hands');
  });

  it.skip('ZMQ peer echo roundtrip < 10ms', () => {
    /* wired by plan 01-03 (INFRA-05) */
  });

  it.skip('hands SIGTERM handler flushes logs cleanly', () => {
    /* wired by plan 01-03 (INFRA-13) */
  });

  it('sqlite_writer WAL roundtrip works', () => {
    // INFRA-03 un-skip: plan 01-02 landed the writer + alembic migration.
    const db = openHandsDb(dbPath);
    try {
      expect(db.pragma('journal_mode', { simple: true })).toBe('wal');

      upsertOpenOrder(db, {
        order_id: 'tracer-1',
        market_id: 'ETHUSDT-29MAY2026',
        side: 'long',
        depth_ticks: 50,
        size_wei: '1000000000000000000',
        rate: 9400,
        status: 'filling',
        placed_at_ts: 1_714_000_000,
        run_id: 'run-tracer',
      });

      const row = db
        .prepare('SELECT order_id, status FROM open_orders WHERE order_id = ?')
        .get('tracer-1') as { order_id: string; status: string };
      expect(row).toEqual({ order_id: 'tracer-1', status: 'filling' });
    } finally {
      db.close();
    }
  });

  it('vitest collection itself works', () => {
    expect(1 + 1).toBe(2);
  });
});
