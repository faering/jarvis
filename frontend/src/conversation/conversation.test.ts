import { envelope, type Envelope } from "@jarvis/protocol";
import { describe, expect, it } from "vitest";
import {
  applyFrame,
  captionsOf,
  EMPTY_CONVERSATION,
  expire,
  isSayId,
  said,
  type Conversation,
} from "./conversation.ts";

const TRACE = "4bf92f3577b34da6a3ce929d0e0e4736";
const frame = (type: string, payload: object, id: string | null = null) =>
  envelope(type, id, { ...payload });
const run = (frames: Envelope[], start = EMPTY_CONVERSATION) =>
  frames.reduce<Conversation>((c, f, i) => applyFrame(c, f, 1000 + i), start);

describe("applyFrame", () => {
  it("follows the loop state and ignores unknown or repeated states", () => {
    const c = run([frame("state", { state: "routing" })]);
    expect(c.loop).toBe("routing");
    expect(applyFrame(c, frame("state", { state: "routing" }), 5)).toBe(c);
    expect(applyFrame(c, frame("state", { state: "dancing" }), 5)).toBe(c);
  });

  it("shows the transcript as your line and starts a new exchange", () => {
    const before = run([
      frame("transcript", { text: "old" }),
      frame("reply", { text: "old answer", done: true, degraded: false }),
    ]);
    const c = applyFrame(
      before,
      frame("transcript", { text: "What's on?" }),
      9,
    );
    expect(c.user).toEqual({ who: "user", text: "What's on?" });
    expect(c.jarvis).toBeNull();
    expect(c.changedAt).toBe(9);
  });

  it("streams reply deltas, then replaces them with the final text", () => {
    const c = run([
      frame("transcript", { text: "Hi" }),
      frame("reply", { delta: "Hel", done: false, degraded: false }),
      frame("reply", { delta: "lo!", done: false, degraded: false }),
    ]);
    expect(c.jarvis).toMatchObject({ text: "Hello!", streaming: true });
    const done = applyFrame(
      c,
      frame("reply", { text: "Hello there!", done: true, degraded: false }),
      2000,
    );
    expect(done.jarvis).toEqual({
      who: "jarvis",
      text: "Hello there!",
      tone: undefined,
    });
  });

  it("starts a fresh reply after a finished one", () => {
    const c = run([
      frame("reply", { text: "First.", done: true, degraded: false }),
      frame("reply", { delta: "Second", done: false, degraded: false }),
    ]);
    expect(c.jarvis?.text).toBe("Second");
  });

  it("marks a degraded reply", () => {
    const c = run([
      frame("reply", { text: "Local.", done: true, degraded: true }),
    ]);
    expect(c.jarvis?.tone).toBe("degraded");
  });

  it("shows errors that answer a say or carry a turn, not others", () => {
    const refused = run([
      frame(
        "error",
        { code: "unavailable", message: "the voice loop is not running" },
        "say-3",
      ),
    ]);
    expect(refused.jarvis).toMatchObject({ tone: "error" });
    expect(refused.jarvis?.text).toContain("the voice loop is not running");
    const traced = run([
      frame("error", { code: "x", message: "m", trace_id: TRACE }),
    ]);
    expect(traced.jarvis?.tone).toBe("error");
    const unrelated = run([
      frame("error", { code: "unknown_type", message: "m" }, "ping-1"),
    ]);
    expect(unrelated).toBe(EMPTY_CONVERSATION);
  });

  it("ignores malformed payloads and other frame types", () => {
    const frames = [
      frame("transcript", { text: 42 }),
      frame("reply", { done: true, degraded: false }),
      frame("reply", { delta: 1, done: false }),
      frame("pong", {}),
    ];
    expect(run(frames)).toBe(EMPTY_CONVERSATION);
  });
});

describe("said, expire and captionsOf", () => {
  it("shows what you typed at once", () => {
    const c = said(EMPTY_CONVERSATION, "Hello", 5);
    expect(captionsOf(c)).toEqual([{ who: "user", text: "Hello" }]);
  });

  it("clears captions only when idle, not streaming, and after the ttl", () => {
    const c = run([
      frame("transcript", { text: "Hi" }),
      frame("reply", { text: "Hello!", done: true, degraded: false }),
    ]); // changedAt 1001, loop null
    expect(expire(c, 1500, 1000)).toBe(c); // too early
    expect(captionsOf(expire(c, 2001, 1000))).toEqual([]);
    const speaking = { ...c, loop: "speaking" as const };
    expect(expire(speaking, 9999, 1000)).toBe(speaking);
    const streaming = run([
      frame("reply", { delta: "…", done: false, degraded: false }),
    ]);
    expect(expire(streaming, 9999, 1)).toBe(streaming);
  });

  it("recognises say ids", () => {
    expect(isSayId("say-1")).toBe(true);
    expect(isSayId("ping-1")).toBe(false);
    expect(isSayId(null)).toBe(false);
  });
});
