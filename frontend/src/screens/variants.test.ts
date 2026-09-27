import { describe, expect, it } from "vitest";
import {
  DEMO_STORAGE_KEY,
  initialDemo,
  initialVariant,
  saveDemo,
  saveVariant,
  stepVariant,
  VARIANT_STORAGE_KEY,
  type KeyValueStore,
} from "./variants.ts";

function memoryStore(init: Record<string, string> = {}): KeyValueStore {
  const data = new Map(Object.entries(init));
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
  };
}

const blocked: KeyValueStore = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
};

describe("initialVariant", () => {
  it("defaults to face", () => {
    expect(initialVariant("", memoryStore(), undefined)).toBe("face");
  });

  it("prefers query > remembered > env", () => {
    const store = memoryStore({ [VARIANT_STORAGE_KEY]: "orb" });
    expect(initialVariant("?screen=ambient", store, "face")).toBe("ambient");
    expect(initialVariant("", store, "ambient")).toBe("orb");
    expect(initialVariant("", memoryStore(), "ambient")).toBe("ambient");
  });

  it("skips invalid values and survives blocked storage", () => {
    const store = memoryStore({ [VARIANT_STORAGE_KEY]: "hologram" });
    expect(initialVariant("?screen=nope", store, "orb")).toBe("orb");
    expect(initialVariant("", blocked, undefined)).toBe("face");
    expect(() => saveVariant(blocked, "orb")).not.toThrow();
  });

  it("remembers the chosen variant", () => {
    const store = memoryStore();
    saveVariant(store, "ambient");
    expect(initialVariant("", store, "face")).toBe("ambient");
  });
});

describe("stepVariant", () => {
  it("wraps in both directions", () => {
    expect(stepVariant("face", 1)).toBe("orb");
    expect(stepVariant("ambient", 1)).toBe("face");
    expect(stepVariant("face", -1)).toBe("ambient");
  });
});

describe("demo mode", () => {
  it("is on by default, overridable by query and remembered", () => {
    const store = memoryStore();
    expect(initialDemo("", store)).toBe(true);
    expect(initialDemo("?demo=0", store)).toBe(false);
    saveDemo(store, false);
    expect(store.getItem(DEMO_STORAGE_KEY)).toBe("0");
    expect(initialDemo("", store)).toBe(false);
    expect(initialDemo("?demo=1", store)).toBe(true);
  });
});
