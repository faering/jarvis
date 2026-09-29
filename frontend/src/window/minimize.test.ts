import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LogRecord } from "../log/format.ts";
import { configureLogging } from "../log/logger.ts";
import { minimizeWindow } from "./minimize.ts";

describe("minimizeWindow", () => {
  let records: LogRecord[] = [];
  beforeEach(() => {
    records = [];
    configureLogging({ level: "TRACE", sinks: [(r) => records.push(r)] });
  });
  afterEach(() => configureLogging({ sinks: [] }));

  it("calls the Rust minimize_window command with its source", async () => {
    const invoke = vi.fn(() => Promise.resolve());
    await minimizeWindow("agent", invoke);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("minimize_window", {
      source: "agent",
    });
    expect(records.at(-1)).toMatchObject({
      level: "INFO",
      message: "window minimized",
      attrs: "source=agent",
    });
  });

  it("logs a failure instead of throwing", async () => {
    // A Rust command's Err(String) rejects with the string.
    const invoke = vi.fn(() => Promise.reject("unknown minimize source: x"));
    await expect(minimizeWindow("keyboard", invoke)).resolves.toBeUndefined();
    const failed = records.at(-1);
    expect(failed).toMatchObject({
      level: "ERROR",
      message: "window minimize failed",
    });
    expect(failed?.attrs).toContain("source=keyboard");
  });

  it("does nothing outside Tauri", async () => {
    await minimizeWindow("keyboard"); // no __TAURI_INTERNALS__ under vitest
    expect(records.at(-1)).toMatchObject({
      level: "DEBUG",
      message: "window minimize skipped: not in Tauri",
    });
  });
});
