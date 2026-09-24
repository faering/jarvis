// Keeps the TS side in step with protocol.schema.json (the source of truth).
import { describe, expect, it } from "vitest";
import schema from "../protocol.schema.json" with { type: "json" };
import {
  asError,
  asHello,
  envelope,
  MESSAGE_TYPES,
  parseEnvelope,
  PROTOCOL_VERSION,
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
    expect(Object.keys(def("hello").properties).sort()).toEqual(
      Object.keys(hello).sort(),
    );
    expect(Object.keys(def("error").properties).sort()).toEqual(
      Object.keys(error).sort(),
    );
  });
});
