// Keeps the TS side in step with protocol.schema.json (the source of truth).
import { describe, expect, it } from "vitest";
import schema from "../protocol.schema.json" with { type: "json" };
import {
  asError,
  asHello,
  ENVELOPE_KEYS,
  envelope,
  isMessageType,
  MESSAGE_TYPES,
  parseEnvelope,
  PROTOCOL_VERSION,
  TRACE_ID_KEY,
  traceIdOf,
} from "./index.ts";

interface PayloadDef {
  properties: Record<string, { type: string }>;
  required: string[];
  examples: Record<string, unknown>[];
}

const defs = schema.$defs as Record<string, PayloadDef>;
const def = (type: string): PayloadDef => {
  const found = defs[type];
  if (!found) throw new Error(`no $defs entry for ${type}`);
  return found;
};
const frame = (type: string, payload: Record<string, unknown>) =>
  JSON.stringify({ v: PROTOCOL_VERSION, type, id: null, payload });
const without = (record: Record<string, unknown>, key: string) =>
  Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));

describe("protocol.schema.json", () => {
  it("has the same protocol version", () => {
    expect(schema.properties.v.const).toBe(PROTOCOL_VERSION);
  });

  it("defines exactly MESSAGE_TYPES", () => {
    expect(Object.keys(defs).sort()).toEqual([...MESSAGE_TYPES].sort());
  });

  it("routes every message type to its payload definition", () => {
    const routed = schema.allOf.map((rule) => [
      rule.if.properties.type.const,
      rule.then.properties.payload.$ref,
    ]);
    expect(routed).toEqual(MESSAGE_TYPES.map((t) => [t, `#/$defs/${t}`]));
  });
});

describe("isMessageType", () => {
  it.each(MESSAGE_TYPES)("accepts %s", (type) => {
    expect(isMessageType(type)).toBe(true);
  });

  it.each(["nope", "", "Ping", "hello "])("rejects %j", (type) => {
    expect(isMessageType(type)).toBe(false);
  });
});

describe("envelope", () => {
  it("builds frames with exactly the schema's properties", () => {
    const built = envelope("ping", "p-1");
    expect(Object.keys(built).sort()).toEqual(
      Object.keys(schema.properties).sort(),
    );
    expect(built.v).toBe(schema.properties.v.const);
  });
});

const examples: [string, Record<string, unknown>][] = MESSAGE_TYPES.flatMap(
  (t) =>
    def(t).examples.map((ex): [string, Record<string, unknown>] => [t, ex]),
);

describe("parseEnvelope", () => {
  it.each(examples)("accepts the %s example", (type, example) => {
    expect(parseEnvelope(frame(type, example))).toEqual({
      v: PROTOCOL_VERSION,
      type,
      id: null,
      payload: example,
    });
  });

  it.each(schema.required)("rejects a frame without %s", (key) => {
    const raw = { v: 0, type: "ping", id: null, payload: {} };
    expect(parseEnvelope(JSON.stringify(without(raw, key)))).toBeNull();
  });

  it.each([
    ["v", "0"],
    ["v", 0.5],
    ["type", ""],
    ["id", 1],
    ["payload", []],
  ])("rejects a bad %s", (key, value) => {
    const raw = { v: 0, type: "ping", id: null, payload: {}, [key]: value };
    expect(parseEnvelope(JSON.stringify(raw))).toBeNull();
  });

  it("knows exactly the schema's envelope properties", () => {
    expect(schema.additionalProperties).toBe(false);
    expect([...ENVELOPE_KEYS].sort()).toEqual(
      Object.keys(schema.properties).sort(),
    );
  });

  it("rejects an unknown top-level key but not an unknown payload field", () => {
    const extra = { v: 0, type: "ping", extra: true };
    expect(parseEnvelope(JSON.stringify(extra))).toBeNull();
    const open = { v: 0, type: "ping", payload: { extra: true } };
    expect(parseEnvelope(JSON.stringify(open))?.payload).toEqual({
      extra: true,
    });
  });

  it("only shape-checks a frame of another version", () => {
    const future = { v: 1, type: "hello", payload: {}, extra: true };
    expect(parseEnvelope(JSON.stringify(future))?.v).toBe(1);
  });

  it("defaults the optional properties like the schema", () => {
    expect(parseEnvelope(JSON.stringify({ v: 0, type: "ping" }))).toEqual({
      v: 0,
      type: "ping",
      id: schema.properties.id.default,
      payload: schema.properties.payload.default,
    });
  });
});

describe("payload guards", () => {
  const hello = def("hello").examples[0]!;
  const error = def("error").examples[0]!;

  it("asHello reads the hello example", () => {
    expect(asHello(hello)).toEqual(hello);
  });

  it.each(def("hello").required)("asHello rejects a hello without %s", (k) => {
    expect(asHello(without(hello, k))).toBeNull();
  });

  it("asError reads the error example", () => {
    expect(asError(error)).toEqual(error);
  });

  it("guards exactly the fields the schema defines", () => {
    // trace_id is read by traceIdOf, for every turn payload alike.
    const fields = (type: string) =>
      Object.keys(def(type).properties)
        .filter((k) => k !== TRACE_ID_KEY)
        .sort();
    expect(fields("hello")).toEqual(Object.keys(hello).sort());
    expect(fields("error")).toEqual(Object.keys(error).sort());
  });
});

describe("trace id", () => {
  const traced = def("state").examples.find((e) => TRACE_ID_KEY in e)!;

  it.each(["error", "state", "transcript", "reply"])(
    "%s may carry the trace id pattern traceIdOf accepts",
    (type) => {
      const prop: unknown = def(type).properties[TRACE_ID_KEY];
      expect(prop).toMatchObject({ pattern: "^[0-9a-f]{32}$" });
    },
  );

  it("reads the trace id from the schema example", () => {
    expect(traceIdOf(traced)).toBe(traced[TRACE_ID_KEY]);
  });

  it("returns null when absent or malformed", () => {
    expect(traceIdOf({ state: "idle" })).toBeNull();
    expect(traceIdOf({ trace_id: "4BF92F35" })).toBeNull();
    expect(traceIdOf({ trace_id: 42 })).toBeNull();
  });
});
