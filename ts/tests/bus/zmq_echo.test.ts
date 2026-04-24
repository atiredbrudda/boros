/**
 * INFRA-05 — cross-language ZMQ round-trip + Zod schema mirror (T-03-03).
 *
 * Two tests here:
 *   1. Pure-TS Push/Pull echo round-trip < 10ms median — confirms the TS
 *      zeromq.js stack is wired end-to-end without depending on Python.
 *   2. Python-generated PlaceCmd JSON parses cleanly through Zod — catches
 *      cross-language schema drift between python/bus/messages.py and
 *      ts/bus/messages.ts.
 */

import { execSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Publisher, Pull, Push, Subscriber } from "zeromq";

import {
	CmdSchema,
	HeartbeatSchema,
	KillCmdSchema,
	LostSiblingSchema,
	PlaceCmdSchema,
} from "../../src/boros_hands/bus/messages.js";

const REPO_ROOT = resolve(__dirname, "../../..");

describe("ZMQ echo + Zod mirror — INFRA-05 / T-03-03", () => {
	let workdir: string;

	beforeEach(() => {
		workdir = mkdtempSync(join(tmpdir(), "b-"));
	});
	afterEach(() => {
		rmSync(workdir, { recursive: true, force: true });
	});

	it("pure-TS Push/Pull round-trip median < 10ms", async () => {
		const endpoint = `ipc://${workdir}/cmd`;
		const push = new Push();
		const pull = new Pull();
		pull.receiveHighWaterMark = 1000;
		await push.bind(endpoint);
		pull.connect(endpoint);
		// Small delay for connect handshake.
		await new Promise((r) => setTimeout(r, 50));

		const latencies: number[] = [];
		const N = 50;
		const msg = PlaceCmdSchema.parse({
			kind: "place",
			order_id: "ord-0",
			market_id: "ETHUSDT-29MAY2026",
			side: "long",
			depth_ticks: 50,
			size_wei: "1",
			rate: 9400,
			run_id: "r",
		});
		for (let i = 0; i < N; i++) {
			const t0 = performance.now();
			await push.send(JSON.stringify({ ...msg, order_id: `ord-${i}` }));
			const [buf] = await pull.receive();
			const t1 = performance.now();
			const parsed = CmdSchema.parse(JSON.parse(buf.toString()));
			expect(parsed.kind).toBe("place");
			latencies.push(t1 - t0);
		}
		const sorted = [...latencies].sort((a, b) => a - b);
		const median = sorted[Math.floor(sorted.length / 2)];
		push.close();
		pull.close();
		expect(median).toBeLessThan(10);
	});

	it('Python model_dump(mode="json") parses through Zod schemas — T-03-03 mirror', () => {
		// Generate canonical JSON from the Python side — any schema drift between
		// Pydantic and Zod will surface here as a ZodError.
		const script = `
from boros_brain.bus.messages import PlaceCmd, CancelCmd, KillCmd, Heartbeat, LostSibling
import json, sys
payload = {
  "place":    PlaceCmd(order_id="o1", market_id="M", side="long", depth_ticks=1, size_wei="1", rate=9400, run_id="r").model_dump(mode="json"),
  "cancel":   CancelCmd(order_id="o1", run_id="r").model_dump(mode="json"),
  "kill":     KillCmd(reason="halt", run_id="r").model_dump(mode="json"),
  "heartbeat": Heartbeat(from_tier="brain", ts_ms=123, run_id="r").model_dump(mode="json"),
  "lost":     LostSibling(observer="brain", missing_since_ts_ms=123, run_id="r").model_dump(mode="json"),
}
json.dump(payload, sys.stdout)
`;
		const out = execSync(
			`uv run python -c '${script.replace(/'/g, "'\\''")}'`,
			{
				cwd: join(REPO_ROOT, "python"),
				encoding: "utf-8",
			},
		);
		const py = JSON.parse(out);

		// Zod round-trip — any field drift throws.
		expect(() => PlaceCmdSchema.parse(py.place)).not.toThrow();
		expect(() => CmdSchema.parse(py.cancel)).not.toThrow();
		expect(() => KillCmdSchema.parse(py.kill)).not.toThrow();
		expect(() => HeartbeatSchema.parse(py.heartbeat)).not.toThrow();
		expect(() => LostSiblingSchema.parse(py.lost)).not.toThrow();
	});
});
