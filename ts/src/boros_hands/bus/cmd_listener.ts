/**
 * ZMQ Pull listener — hands-side.
 *
 * Two sockets (cmd + kill). The kill drain loop runs independently; in
 * `drainKill + drainCmd` consumption it takes priority because `for await`
 * on the kill socket yields immediately when a message is available. Kill
 * handler callbacks must be fast (milliseconds) so they don't starve cmd.
 *
 * T-03-04 mitigation: every inbound buffer is validated via Zod `.parse()`
 * before the user callback runs. A parse failure throws — callers should
 * wrap `drainCmd / drainKill` in a try/catch and log the error.
 */

import { Pull } from 'zeromq';

import {
  type CancelCmd,
  CmdSchema,
  type KillCmd,
  KillCmdSchema,
  type PlaceCmd,
} from './messages.js';

export type CmdHandler = (cmd: PlaceCmd | CancelCmd) => void | Promise<void>;
export type KillHandler = (cmd: KillCmd) => void | Promise<void>;

export class CmdListener {
  private cmdSock = new Pull();
  private killSock = new Pull();
  private running = true;

  async connect(cmdEndpoint: string, killEndpoint: string): Promise<void> {
    this.cmdSock.receiveHighWaterMark = 1000;
    this.killSock.receiveHighWaterMark = 1000;
    this.cmdSock.connect(cmdEndpoint);
    this.killSock.connect(killEndpoint);
  }

  /** Drain the kill socket — runs as an independent task so KILLs never wait on PLACE. */
  async drainKill(onKill: KillHandler): Promise<void> {
    for await (const [buf] of this.killSock) {
      if (!this.running) break;
      // Validate against Zod schema — T-03-04 guard. Parse failure throws.
      const msg = KillCmdSchema.parse(JSON.parse(buf.toString()));
      await onKill(msg);
    }
  }

  /** Drain the cmd socket — PlaceCmd / CancelCmd only. KillCmd is defense-in-depth skipped. */
  async drainCmd(onCmd: CmdHandler): Promise<void> {
    for await (const [buf] of this.cmdSock) {
      if (!this.running) break;
      const parsed = CmdSchema.parse(JSON.parse(buf.toString()));
      if (parsed.kind === 'kill') {
        // Should never arrive on this socket — log and skip as defense in depth.
        continue;
      }
      await onCmd(parsed);
    }
  }

  stop(): void {
    this.running = false;
    this.cmdSock.close();
    this.killSock.close();
  }
}
