/**
 * Agent <-> app WebSocket contract, envelope v0 — the TS side of
 * ../protocol.schema.json (the single source of truth; index.test.ts fails on
 * drift). The Python side is agent/src/jarvis_agent/protocol.py.
 *
 * Every frame is `{ v: 0, type, id, payload }`.
 */

/** Must equal the schema's `properties.v.const`. */
export const PROTOCOL_VERSION = 0;

/** Every message type in the schema's `$defs`. */
export const MESSAGE_TYPES = [
  "hello",
  "ping",
  "pong",
  "error",
  "say",
  "state",
  "transcript",
  "reply",
] as const;

export type MessageType = (typeof MESSAGE_TYPES)[number];

export function isMessageType(type: string): type is MessageType {
  return (MESSAGE_TYPES as readonly string[]).includes(type);
}

export interface Envelope {
  v: number;
  type: string;
  id: string | null;
  payload: Record<string, unknown>;
}

/** Server greeting sent on connect. */
export interface HelloPayload {
  protocol: number;
  agent: string;
}

export interface ErrorPayload {
  code: string;
  message: string;
}

export function envelope(
  type: string,
  id: string | null = null,
  payload: Record<string, unknown> = {},
): Envelope {
  return { v: PROTOCOL_VERSION, type, id, payload };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Parse one text frame; returns null for anything that is not an envelope. */
export function parseEnvelope(raw: string): Envelope | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(data)) return null;
  const { v, type, id = null, payload = {} } = data;
  if (typeof v !== "number" || typeof type !== "string" || type === "") {
    return null;
  }
  if ((id !== null && typeof id !== "string") || !isRecord(payload)) {
    return null;
  }
  return { v, type, id, payload };
}

export function asHello(payload: Record<string, unknown>): HelloPayload | null {
  const { protocol, agent } = payload;
  if (typeof protocol !== "number" || typeof agent !== "string") return null;
  return { protocol, agent };
}

export function asError(payload: Record<string, unknown>): ErrorPayload {
  const { code, message } = payload;
  return {
    code: typeof code === "string" ? code : "unknown",
    message: typeof message === "string" ? message : "",
  };
}
