import { describe, expect, it } from "vitest";
import {
  DEFAULT_SCREEN,
  isScreenId,
  SCREEN_IDS,
  SCREENS,
} from "./catalogue.ts";

describe("screen catalogue", () => {
  it("defaults to the face", () => {
    expect(DEFAULT_SCREEN).toBe("face");
    expect(SCREEN_IDS).toContain(DEFAULT_SCREEN);
  });

  it.each(SCREEN_IDS)("%s is described and loads a component", async (id) => {
    const entry = SCREENS[id];
    expect(entry.name).not.toBe("");
    expect(entry.description).not.toBe("");
    const { default: Screen } = await entry.load();
    expect(typeof Screen).toBe("function");
  });

  it("recognises only catalogue ids", () => {
    expect(isScreenId("orb")).toBe(true);
    expect(isScreenId("hologram")).toBe(false);
    expect(isScreenId("toString")).toBe(false);
    expect(isScreenId(undefined)).toBe(false);
  });
});
