import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WebSocketServer } from "ws";
import { AgentClient } from "../agent/client.ts";
import { isTypingKey } from "../conversation/keys.ts";
import { bindWindowControls, isMinimizeKey } from "./controls.ts";

type Mods = Partial<
  Record<"ctrlKey" | "altKey" | "metaKey" | "shiftKey", boolean>
>;

const key = (k: string, mods: Mods = {}) => ({
  key: k,
  ctrlKey: false,
  altKey: false,
  metaKey: false,
  shiftKey: false,
  ...mods,
});

/** A cancelable keydown as the window would get it (vitest runs without a DOM). */
function keydown(k: string, mods: Mods = {}) {
  return Object.assign(
    new Event("keydown", { cancelable: true }),
    key(k, mods),
  );
}

const cleanup: (() => unknown)[] = [];
afterEach(async () => {
  for (const fn of cleanup.splice(0)) await fn();
});

describe("the minimize key", () => {
  it("is Ctrl+M only", () => {
    expect(isMinimizeKey(key("m", { ctrlKey: true }))).toBe(true);
    expect(isMinimizeKey(key("M", { ctrlKey: true }))).toBe(true); // caps lock
    expect(isMinimizeKey(key("m"))).toBe(false);
    for (const mod of ["altKey", "metaKey", "shiftKey"] as const)
      expect(isMinimizeKey(key("m", { ctrlKey: true, [mod]: true }))).toBe(
        false,
      );
  });

  it("doesn't open the typing input, while a plain m does", () => {
    expect(isTypingKey(key("m", { ctrlKey: true }))).toBe(false);
    expect(isTypingKey(key("m"))).toBe(true);
  });
});

describe("bindWindowControls", () => {
  const noAgent = { onCommand: () => () => {} };

  it("minimizes on Ctrl+M and swallows the key", () => {
    const target = new EventTarget();
    const minimize = vi.fn();
    cleanup.push(bindWindowControls({ agent: noAgent, target, minimize }));
    const event = keydown("m", { ctrlKey: true });
    target.dispatchEvent(event);
    expect(minimize).toHaveBeenCalledExactlyOnceWith("keyboard");
    expect(event.defaultPrevented).toBe(true);
  });

  it("leaves a plain m to the typing input", () => {
    const target = new EventTarget();
    const minimize = vi.fn();
    cleanup.push(bindWindowControls({ agent: noAgent, target, minimize }));
    const event = keydown("m");
    target.dispatchEvent(event);
    expect(minimize).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("stops listening once unbound", () => {
    const target = new EventTarget();
    const minimize = vi.fn();
    bindWindowControls({ agent: noAgent, target, minimize })();
    target.dispatchEvent(keydown("m", { ctrlKey: true }));
    expect(minimize).not.toHaveBeenCalled();
  });

  it("minimizes on the agent's window.minimize command", async () => {
    const server = new WebSocketServer({ port: 0, host: "127.0.0.1" });
    await new Promise<void>((resolve) => server.once("listening", resolve));
    server.on("connection", (socket) => {
      const send = (type: string, payload: object) =>
        socket.send(JSON.stringify({ v: 0, type, id: null, payload }));
      send("hello", { protocol: 0, agent: "1.2.3" });
      send("command", { name: "window.minimize" });
    });
    const { port } = server.address() as AddressInfo;
    const agent = new AgentClient({ url: `ws://127.0.0.1:${port}/ws` });
    const minimize = vi.fn();
    const unbind = bindWindowControls({
      agent,
      target: new EventTarget(),
      minimize,
    });
    cleanup.push(
      unbind,
      () => agent.stop(),
      () => {
        for (const client of server.clients) client.terminate();
        return new Promise((resolve) => server.close(resolve));
      },
    );
    agent.start();
    await vi.waitFor(() => expect(minimize).toHaveBeenCalledWith("agent"));
  });
});
