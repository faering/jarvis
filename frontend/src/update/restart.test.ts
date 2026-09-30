import { describe, expect, it, vi } from "vitest";
import { onUpdateInstalled, restartApp } from "./restart.ts";

describe("restartApp", () => {
  it("asks the Rust side to restart", async () => {
    const run = vi.fn(() => Promise.resolve());
    await restartApp("0.3.0", run);
    expect(run).toHaveBeenCalledWith("restart_app");
  });

  it("logs a failure instead of throwing", async () => {
    const run = vi.fn(() => Promise.reject(new Error("not allowed")));
    await expect(restartApp("0.3.0", run)).resolves.toBeUndefined();
  });
});

describe("onUpdateInstalled", () => {
  it("does nothing outside Tauri", () => {
    const onUpdate = vi.fn();
    const off = onUpdateInstalled(onUpdate);
    off();
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
