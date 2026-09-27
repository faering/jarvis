import type { ConnectionState } from "../agent/client.ts";

/**
 * What Jarvis is doing, as the default screen shows it (spike #133).
 * App-local for now: the protocol's `state` frame (#118/#120) carries the loop
 * state, and a future `expression` field may carry the emotion hint.
 */
export const PRESENCE_STATES = [
  "idle",
  "listening",
  "thinking",
  "speaking",
  "offloaded",
  "disconnected",
] as const;
export type PresenceState = (typeof PRESENCE_STATES)[number];

export const EXPRESSIONS = [
  "neutral",
  "happy",
  "curious",
  "concerned",
  "amused",
] as const;
export type Expression = (typeof EXPRESSIONS)[number];

/** A line shown by the conversation overlay (demo only for now). */
export interface Caption {
  who: "user" | "jarvis";
  text: string;
}

export interface Presence {
  state: PresenceState;
  expression: Expression;
  caption?: Caption;
}

/** Loop states the agent sends in its `state` frame (#118). */
export type LoopState =
  "idle" | "listening" | "routing" | "speaking" | "offloaded";

/** Map an agent loop state to a presence state (`routing` reads as thinking). */
export function presenceFromLoop(loop: LoopState): PresenceState {
  return loop === "routing" ? "thinking" : loop;
}

export interface PresenceInputs {
  connection: ConnectionState;
  /** Last loop state from the agent, once the protocol carries it. */
  loop?: LoopState | null;
  /** Demo driver output; when set it wins, so screens are evaluable offline. */
  demo?: Presence | null;
}

/** Combine the real connection, the agent loop state and the demo driver. */
export function resolvePresence({
  connection,
  loop,
  demo,
}: PresenceInputs): Presence {
  if (demo) return demo;
  if (connection !== "open") {
    return { state: "disconnected", expression: "neutral" };
  }
  return {
    state: loop ? presenceFromLoop(loop) : "idle",
    expression: "neutral",
  };
}

const STATE_LABELS: Record<PresenceState, string> = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  offloaded: "working in the background",
  disconnected: "disconnected",
};

/** Human-readable description, used for aria labels and the switcher. */
export function describePresence({ state, expression }: Presence): string {
  const base = STATE_LABELS[state];
  return expression === "neutral" ? base : `${base}, ${expression}`;
}
