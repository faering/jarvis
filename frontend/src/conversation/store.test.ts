import { envelope } from "@jarvis/protocol";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { captionsOf } from "./conversation.ts";
import { ConversationStore } from "./store.ts";

describe("ConversationStore", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const make = () =>
    new ConversationStore({ ttlMs: 1000, now: () => Date.now() });

  it("notifies on changes and not on no-ops", () => {
    const store = make();
    const seen = vi.fn();
    store.subscribe(seen);
    store.apply(envelope("state", null, { state: "routing" }));
    store.apply(envelope("state", null, { state: "routing" }));
    expect(seen).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().loop).toBe("routing");
  });

  it("clears the captions a ttl after the last change once idle", () => {
    const store = make();
    store.said("Hello");
    store.apply(envelope("state", null, { state: "routing" }));
    vi.advanceTimersByTime(1500);
    expect(captionsOf(store.getSnapshot())).toHaveLength(1); // still busy
    store.apply(
      envelope("reply", null, { text: "Hi!", done: true, degraded: false }),
    );
    store.apply(envelope("state", null, { state: "idle" }));
    vi.advanceTimersByTime(999);
    expect(captionsOf(store.getSnapshot())).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(captionsOf(store.getSnapshot())).toEqual([]);
  });

  it("forgets the loop state on disconnect but keeps the captions", () => {
    const store = make();
    store.said("Hello");
    store.apply(envelope("state", null, { state: "speaking" }));
    store.disconnected();
    expect(store.getSnapshot().loop).toBeNull();
    expect(captionsOf(store.getSnapshot())).toHaveLength(1);
    store.dispose();
  });
});
