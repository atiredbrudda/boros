/**
 * INFRA-07 — pino logger emits the minimum shared record shape + carries run_id
 * through AsyncLocalStorage.
 */

import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { configureHandsLogger, ctxStore, log } from '../src/boros_hands/logger.js';

const MIN_FIELDS = ['ts', 'level', 'event', 'run_id', 'tier', 'logger', 'pid'] as const;

function findLogFile(logsDir: string, runId: string): string {
  // <logsDir>/<YYYY-MM-DD>/<runId>.hands.log.jsonl
  const dateDirs = readdirSync(logsDir);
  for (const date of dateDirs) {
    const candidate = join(logsDir, date, `${runId}.hands.log.jsonl`);
    try {
      readFileSync(candidate);
      return candidate;
    } catch {
      /* not here */
    }
  }
  throw new Error(`no log file for run_id=${runId} under ${logsDir}`);
}

describe('pino hands logger — INFRA-07', () => {
  let workdir: string;

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'boros-logger-'));
  });

  afterEach(() => {
    rmSync(workdir, { recursive: true, force: true });
  });

  it('emits minimum field set with correct run_id + tier', () => {
    configureHandsLogger('RUNID_ABC', workdir);
    ctxStore.run({ run_id: 'RUNID_ABC', tier: 'hands' }, () => {
      log().info({ event: 'test_event', extra_key: 'x' });
    });

    const path = findLogFile(workdir, 'RUNID_ABC');
    const firstLine = readFileSync(path, 'utf-8').split('\n').filter(Boolean)[0];
    const rec = JSON.parse(firstLine);
    for (const f of MIN_FIELDS) {
      expect(rec).toHaveProperty(f);
    }
    expect(rec.run_id).toBe('RUNID_ABC');
    expect(rec.tier).toBe('hands');
    expect(rec.event).toBe('test_event');
    expect(rec.extra_key).toBe('x');
    expect(typeof rec.pid).toBe('number');
    expect(typeof rec.ts).toBe('string');
  });

  it('mixin falls back to configure-time run_id when outside ctxStore.run', () => {
    configureHandsLogger('RUNID_DEFAULT', workdir);
    log().info({ event: 'no_context' });

    const path = findLogFile(workdir, 'RUNID_DEFAULT');
    const firstLine = readFileSync(path, 'utf-8').split('\n').filter(Boolean)[0];
    const rec = JSON.parse(firstLine);
    expect(rec.run_id).toBe('RUNID_DEFAULT');
    expect(rec.tier).toBe('hands');
  });

  it('propagates run_id across awaited async work via AsyncLocalStorage', async () => {
    configureHandsLogger('RUNID_ASYNC', workdir);

    async function inner(tag: string): Promise<void> {
      // Micro-yield to ensure the ALS binding survives across the await boundary.
      await new Promise((r) => setTimeout(r, 1));
      log().info({ event: 'inner_event', tag });
    }

    await ctxStore.run({ run_id: 'RUNID_ASYNC', tier: 'hands' }, async () => {
      await Promise.all([inner('a'), inner('b')]);
    });

    const path = findLogFile(workdir, 'RUNID_ASYNC');
    const records = readFileSync(path, 'utf-8')
      .split('\n')
      .filter(Boolean)
      .map((l) => JSON.parse(l));
    const innerRecs = records.filter((r) => r.event === 'inner_event');
    expect(innerRecs).toHaveLength(2);
    expect(innerRecs.every((r) => r.run_id === 'RUNID_ASYNC')).toBe(true);
    expect(new Set(innerRecs.map((r) => r.tag))).toEqual(new Set(['a', 'b']));
  });
});
