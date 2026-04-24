/**
 * 5s heartbeat send + 15s (3-miss) lost-sibling monitor — TS mirror of
 * python/src/boros_brain/bus/heartbeat.py.
 *
 * Production settings come from the brain-side BotConfig; hands receives them
 * via env-injected knobs at boot (plan 01-03 Task 2 wires the env injection).
 */

import type { EventPublisher } from './event_publisher.js';

export const LOST_SIBLING_EVENT = 'lost_sibling';

export class HeartbeatMonitor {
  public lastPeerHeartbeatMs: number;
  private stopped = false;
  private emittedLost = false;
  private readonly timeoutMs: number;

  constructor(
    private events: EventPublisher,
    private tier: 'brain' | 'hands',
    private runId: string,
    private intervalS: number = 5.0,
    private timeoutMisses: number = 3,
  ) {
    this.timeoutMs = intervalS * timeoutMisses * 1000;
    this.lastPeerHeartbeatMs = Date.now();
  }

  /** Publish a heartbeat every `intervalS` until `stop()` is called. */
  async sendLoop(): Promise<void> {
    while (!this.stopped) {
      await this.events.publish({
        kind: 'heartbeat',
        from_tier: this.tier,
        ts_ms: Date.now(),
        run_id: this.runId,
      });
      await new Promise((r) => setTimeout(r, this.intervalS * 1000));
    }
  }

  /** Fire LostSibling once after `timeoutMisses` consecutive missed intervals. */
  async monitorLoop(): Promise<void> {
    while (!this.stopped) {
      await new Promise((r) => setTimeout(r, this.intervalS * 1000));
      if (this.stopped) return;
      const elapsed = Date.now() - this.lastPeerHeartbeatMs;
      if (elapsed > this.timeoutMs && !this.emittedLost) {
        await this.events.publish({
          kind: 'lost_sibling',
          observer: this.tier,
          missing_since_ts_ms: this.lastPeerHeartbeatMs,
          run_id: this.runId,
        });
        this.emittedLost = true;
      } else if (elapsed <= this.timeoutMs) {
        this.emittedLost = false; // recovered
      }
    }
  }

  recordPeerHeartbeat(tsMs: number): void {
    this.lastPeerHeartbeatMs = tsMs;
  }

  stop(): void {
    this.stopped = true;
  }
}
