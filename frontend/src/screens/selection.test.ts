import { describe, expect, it } from "vitest";
import {
  DEMO_STORAGE_KEY,
  initialDemo,
  initialScreen,
  saveDemo,
  saveScreen,
  stepScreen,
  SCREEN_STORAGE_KEY,
  type KeyValueStore,
} from "./selection.ts";

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

describe("initialScreen", () => {
  it("defaults to face", () => {
    expect(initialScreen("", memoryStore(), undefined)).toBe("face");
  });

  it("prefers query > remembered > env", () => {
    const store = memoryStore({ [SCREEN_STORAGE_KEY]: "orb" });
    expect(initialScreen("?screen=ambient", store, "face")).toBe("ambient");
    expect(initialScreen("", store, "ambient")).toBe("orb");
    expect(initialScreen("", memoryStore(), "ambient")).toBe("ambient");
  });

  it("skips invalid values and survives blocked storage", () => {
    const store = memoryStore({ [SCREEN_STORAGE_KEY]: "hologram" });
    expect(initialScreen("?screen=nope", store, "orb")).toBe("orb");
    expect(initialScreen("", blocked, undefined)).toBe("face");
    expect(() => saveScreen(blocked, "orb")).not.toThrow();
  });

  it("remembers the chosen screen", () => {
    const store = memoryStore();
    saveScreen(store, "ambient");
    expect(initialScreen("", store, "face")).toBe("ambient");
  });
});

describe("stepScreen", () => {
  it("wraps in both directions", () => {
    expect(stepScreen("face", 1)).toBe("orb");
    expect(stepScreen("ambient", 1)).toBe("face");
    expect(stepScreen("face", -1)).toBe("ambient");
  });
});

describe("demo mode", () => {
  it("defaults to the build's fallback, overridable by query and remembered", () => {
    const store = memoryStore();
    expect(initialDemo("", store, true)).toBe(true); // dev build
    expect(initialDemo("", store, false)).toBe(false); // production build
    expect(initialDemo("?demo=0", store, true)).toBe(false);
    expect(initialDemo("?demo=1", store, false)).toBe(true);
    saveDemo(store, false);
    expect(store.getItem(DEMO_STORAGE_KEY)).toBe("0");
    expect(initialDemo("", store, true)).toBe(false);
    saveDemo(store, true);
    expect(initialDemo("", store, false)).toBe(true);
  });
});
