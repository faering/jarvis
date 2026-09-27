import { asError, type Envelope } from "@jarvis/protocol";
import type { Caption, LoopState } from "../presence/presence.ts";

/**
 * The typed conversation as the screen shows it: the loop state and the last
 * exchange (what you said, what Jarvis is answering). Fed by the agent's turn
 * frames (`state`, `transcript`, `reply`, `error`).
 */
export interface Conversation {
  loop: LoopState | null;
  user: Caption | null;
  jarvis: Caption | null;
  /** Epoch ms of the last text change; captions expire from here. */
  changedAt: number;
}

export const EMPTY_CONVERSATION: Conversation = {
  loop: null,
  user: null,
  jarvis: null,
  changedAt: 0,
};

const LOOP_STATES: ReadonlySet<string> = new Set<LoopState>([
  "idle",
  "listening",
  "routing",
  "speaking",
  "offloaded",
]);

function isLoopState(value: unknown): value is LoopState {
  return typeof value === "string" && LOOP_STATES.has(value);
}

/** The error frames that answer a typed request (ours are `say-N`). */
export function isSayId(id: string | null): boolean {
  return id?.startsWith("say-") ?? false;
}

/** What you typed, shown at once (the agent's `transcript` confirms it). */
export function said(c: Conversation, text: string, now: number): Conversation {
  return { ...c, user: { who: "user", text }, jarvis: null, changedAt: now };
}

/** Apply one agent frame; frames that change nothing return `c` itself. */
export function applyFrame(
  c: Conversation,
  frame: Envelope,
  now: number,
): Conversation {
  const p = frame.payload;
  switch (frame.type) {
    case "state":
      return isLoopState(p.state) && p.state !== c.loop
        ? { ...c, loop: p.state }
        : c;
    case "transcript":
      return typeof p.text === "string" ? said(c, p.text, now) : c;
    case "reply": {
      const tone = p.degraded === true ? ("degraded" as const) : undefined;
      if (p.done === true && typeof p.text === "string") {
        const jarvis: Caption = { who: "jarvis", text: p.text, tone };
        return { ...c, jarvis, changedAt: now };
      }
      if (p.done === false && typeof p.delta === "string") {
        const before = c.jarvis?.streaming ? c.jarvis.text : "";
        const jarvis: Caption = {
          who: "jarvis",
          text: before + p.delta,
          streaming: true,
          tone,
        };
        return { ...c, jarvis, changedAt: now };
      }
      return c;
    }
    case "error": {
      // Only errors answering a turn; connection-level ones show in the status pill.
      if (!isSayId(frame.id) && typeof p.trace_id !== "string") return c;
      const { message } = asError(p);
      const text = `I can't answer that right now: ${message || "unknown error"}.`;
      return {
        ...c,
        jarvis: { who: "jarvis", text, tone: "error" },
        changedAt: now,
      };
    }
    default:
      return c;
  }
}

/** Drop the captions once the loop is idle and they have shown for `ttlMs`. */
export function expire(
  c: Conversation,
  now: number,
  ttlMs: number,
): Conversation {
  const quiet = c.loop === null || c.loop === "idle";
  const hasText = c.user !== null || c.jarvis !== null;
  if (!quiet || !hasText || c.jarvis?.streaming || now - c.changedAt < ttlMs) {
    return c;
  }
  return { ...c, user: null, jarvis: null };
}

/** The captions to show, oldest first. */
export function captionsOf(c: Conversation): Caption[] {
  return [c.user, c.jarvis].filter((line): line is Caption => line !== null);
}
