import { describe, expect, it } from "vitest";
import type { ConnectionState } from "../agent/client.ts";
import {
  describePresence,
  presenceFromLoop,
  resolvePresence,
  type Presence,
} from "./presence.ts";

describe("resolvePresence", () => {
  it.each<ConnectionState>([
    "connecting",
    "reconnecting",
    "incompatible",
    "closed",
  ])("shows disconnected while the connection is %s", (connection) => {
    expect(resolvePresence({ connection })).toEqual({
      state: "disconnected",
      expression: "neutral",
      captions: [],
    });
  });

  it("is idle when connected and no loop state is known", () => {
    expect(resolvePresence({ connection: "open" }).state).toBe("idle");
  });

  it("follows the agent loop state when connected", () => {
    expect(
      resolvePresence({ connection: "open", loop: "speaking" }).state,
    ).toBe("speaking");
    expect(
      resolvePresence({ connection: "closed", loop: "speaking" }).state,
    ).toBe("disconnected");
  });

  it("carries the captions and looks concerned when a reply failed", () => {
    const ok = [{ who: "jarvis", text: "Hi." }] as const;
    expect(resolvePresence({ connection: "open", captions: ok })).toMatchObject(
      {
        captions: ok,
        expression: "neutral",
      },
    );
    const failed = [{ who: "jarvis", text: "No.", tone: "error" }] as const;
    expect(
      resolvePresence({ connection: "open", captions: failed }).expression,
    ).toBe("concerned");
  });

  it("lets the demo driver win over the connection", () => {
    const demo: Presence = { state: "listening", expression: "curious" };
    expect(resolvePresence({ connection: "closed", demo })).toBe(demo);
  });
});

describe("presenceFromLoop", () => {
  it("reads routing as thinking and passes the rest through", () => {
    expect(presenceFromLoop("routing")).toBe("thinking");
    expect(presenceFromLoop("offloaded")).toBe("offloaded");
    expect(presenceFromLoop("idle")).toBe("idle");
  });
});

describe("describePresence", () => {
  it("adds non-neutral expressions", () => {
    expect(describePresence({ state: "idle", expression: "neutral" })).toBe(
      "idle",
    );
    expect(describePresence({ state: "speaking", expression: "happy" })).toBe(
      "speaking, happy",
    );
  });
});
