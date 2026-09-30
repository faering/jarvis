import { describe, expect, it } from "vitest";
import {
  type Activity,
  isQuiet,
  RestartWhenQuiet,
  type Timers,
} from "./restartWhenQuiet.ts";

const idle: Activity = { state: "idle", typing: false, captions: 0 };

/** Timers the test fires by hand. */
function fakeTimers() {
  const pending = new Map<number, { run: () => void; ms: number }>();
  let next = 0;
  const timers: Timers = {
    set: (run, ms) => {
      pending.set(++next, { run, ms });
      return next;
    },
    clear: (handle) => pending.delete(handle as number),
  };
  const fire = () => {
    const due = [...pending.entries()];
    pending.clear();
    for (const [, { run }] of due) run();
  };
  return { timers, pending, fire };
}

function setup() {
  const restarts: string[] = [];
  const t = fakeTimers();
  const r = new RestartWhenQuiet((v) => restarts.push(v), t.timers, 10_000);
  return { r, restarts, ...t };
}

describe("isQuiet", () => {
  it("is quiet when idle or disconnected, with nothing typed or shown", () => {
    expect(isQuiet(idle)).toBe(true);
    expect(isQuiet({ ...idle, state: "disconnected" })).toBe(true);
  });

  it.each(["listening", "thinking", "speaking", "offloaded"] as const)(
    "is busy while %s",
    (state) => {
      expect(isQuiet({ ...idle, state })).toBe(false);
    },
  );

  it("is busy while typing or while captions are on screen", () => {
    expect(isQuiet({ ...idle, typing: true })).toBe(false);
    expect(isQuiet({ ...idle, captions: 2 })).toBe(false);
  });
});

describe("RestartWhenQuiet", () => {
  it("never restarts without an update", () => {
    const { r, pending } = setup();
    r.activity(idle);
    expect(pending.size).toBe(0);
  });

  it("restarts once, after the quiet period", () => {
    const { r, restarts, pending, fire } = setup();
    r.activity(idle);
    r.updateInstalled("0.3.0");
    expect([...pending.values()].map((p) => p.ms)).toEqual([10_000]);
    expect(restarts).toEqual([]);
    fire();
    expect(restarts).toEqual(["0.3.0"]);
    r.activity(idle);
    r.updateInstalled("0.3.1");
    expect(pending.size).toBe(0); // restarting already
  });

  it("waits while busy, and starts the quiet period over", () => {
    const { r, restarts, pending, fire } = setup();
    r.updateInstalled("0.3.0");
    r.activity({ ...idle, state: "speaking" });
    expect(pending.size).toBe(0);
    r.activity(idle);
    expect(pending.size).toBe(1);
    r.activity({ ...idle, typing: true }); // busy again: the countdown is dropped
    expect(pending.size).toBe(0);
    r.activity(idle);
    fire();
    expect(restarts).toEqual(["0.3.0"]);
  });

  it("keeps one countdown across quiet updates", () => {
    const { r, pending } = setup();
    r.updateInstalled("0.3.0");
    r.activity(idle);
    r.activity({ ...idle, state: "disconnected" });
    expect(pending.size).toBe(1);
  });

  it("does nothing once disposed", () => {
    const { r, pending } = setup();
    r.updateInstalled("0.3.0");
    r.activity(idle);
    r.dispose();
    expect(pending.size).toBe(0);
    r.activity(idle);
    expect(pending.size).toBe(0);
  });
});
