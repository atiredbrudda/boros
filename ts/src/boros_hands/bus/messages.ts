/**
 * ZMQ message Zod schemas — hand-mirrored from python/src/boros_brain/bus/messages.py.
 *
 * Cross-language drift (T-03-03) is caught by `test_zmq_schema_mirror` in
 * ts/tests/bus/zmq_echo.test.ts which round-trips a Pydantic `model_dump(mode='json')`
 * through `z.parse(...)` and asserts no ValidationError.
 *
 * Every schema uses `.strict()` so unknown fields from the peer (T-03-04 unvalidated
 * input) raise a parse error rather than silently leaking through.
 */

import { z } from "zod";

export const PlaceCmdSchema = z
	.object({
		kind: z.literal("place"),
		order_id: z.string(),
		market_id: z.string(),
		side: z.enum(["long", "short"]),
		depth_ticks: z.number().int(),
		size_wei: z.string(),
		rate: z.number().int(),
		run_id: z.string(),
	})
	.strict();

export const CancelCmdSchema = z
	.object({
		kind: z.literal("cancel"),
		order_id: z.string(),
		run_id: z.string(),
	})
	.strict();

export const KillCmdSchema = z
	.object({
		kind: z.literal("kill"),
		reason: z.string(),
		run_id: z.string(),
	})
	.strict();

export const HeartbeatSchema = z
	.object({
		kind: z.literal("heartbeat"),
		from_tier: z.enum(["brain", "hands"]),
		ts_ms: z.number().int(),
		run_id: z.string(),
	})
	.strict();

export const LostSiblingSchema = z
	.object({
		kind: z.literal("lost_sibling"),
		observer: z.enum(["brain", "hands"]),
		missing_since_ts_ms: z.number().int(),
		run_id: z.string(),
	})
	.strict();

export const RunManifestAnnounceSchema = z
	.object({
		kind: z.literal("run_manifest_announce"),
		run_id: z.string(),
		started_at: z.string(),
		parent_run_id: z.string().nullable().optional(),
	})
	.strict();

/** Discriminated union of cmd messages — used by CmdListener for validation. */
export const CmdSchema = z.discriminatedUnion("kind", [
	PlaceCmdSchema,
	CancelCmdSchema,
	KillCmdSchema,
]);

export type PlaceCmd = z.infer<typeof PlaceCmdSchema>;
export type CancelCmd = z.infer<typeof CancelCmdSchema>;
export type KillCmd = z.infer<typeof KillCmdSchema>;
export type Heartbeat = z.infer<typeof HeartbeatSchema>;
export type LostSibling = z.infer<typeof LostSiblingSchema>;
export type RunManifestAnnounce = z.infer<typeof RunManifestAnnounceSchema>;
