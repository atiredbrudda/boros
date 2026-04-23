/**
 * Hands-side config stub.
 *
 * TODO: generate from the Python Pydantic schema in a later plan. For Wave 0 the
 * hands process does not read any config directly — all knob values arrive over
 * ZMQ as part of each command envelope (plan 01-03).
 */

export type BotConfig = Record<string, unknown>;
