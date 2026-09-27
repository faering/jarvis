import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_SCRIPT, DemoDriver, type DemoStep } from "./demoDriver.ts";
import { EXPRESSIONS, PRESENCE_STATES } from "./presence.ts";

const script: DemoStep[] = [
  { state: "idle", expression: "neutral", durationMs: 1000 },
  { state: "listening", expression: "curious", durationMs: 500 },
  { state: "speaking", expression: "happy", durationMs: 2000 },
];

describe("DemoDriver", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("steps through the script on each step's own timer and wraps", () => {
    const driver = new DemoDriver(script);
    driver.start();
    expect(driver.getSnapshot().state).toBe("idle");
    vi.advanceTimersByTime(999);
    expect(driver.getSnapshot().state).toBe("idle");
    vi.advanceTimersByTime(1);
    expect(driver.getSnapshot().state).toBe("listening");
    vi.advanceTimersByTime(500);
    expect(driver.getSnapshot().state).toBe("speaking");
    vi.advanceTimersByTime(2000);
    expect(driver.getSnapshot().state).toBe("idle");
  });

  it("advances on tap and restarts the step timer", () => {
    const driver = new DemoDriver(script);
    driver.start();
    vi.advanceTimersByTime(900);
    driver.advance();
    expect(driver.getSnapshot().state).toBe("listening");
    vi.advanceTimersByTime(499);
    expect(driver.getSnapshot().state).toBe("listening");
    vi.advanceTimersByTime(1);
    expect(driver.getSnapshot().state).toBe("speaking");
  });

  it("notifies subscribers and stops cleanly", () => {
    const driver = new DemoDriver(script);
    const listener = vi.fn();
    const unsubscribe = driver.subscribe(listener);
    driver.start();
    vi.advanceTimersByTime(1000);
    expect(listener).toHaveBeenCalledTimes(1);
    driver.stop();
    vi.advanceTimersByTime(10_000);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(driver.isRunning).toBe(false);
    unsubscribe();
    driver.advance(); // a manual advance still works while stopped
    expect(listener).toHaveBeenCalledTimes(1);
    expect(driver.getSnapshot().state).toBe("speaking");
  });

  it("the default script covers every state and expression", () => {
    const states = new Set(DEMO_SCRIPT.map((s) => s.state));
    const expressions = new Set(DEMO_SCRIPT.map((s) => s.expression));
    expect([...states].sort()).toEqual([...PRESENCE_STATES].sort());
    expect([...expressions].sort()).toEqual([...EXPRESSIONS].sort());
  });
});
