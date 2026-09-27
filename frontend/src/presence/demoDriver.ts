import type { Presence } from "./presence.ts";

export interface DemoStep extends Presence {
  /** How long the step shows before the driver moves on (ms). */
  durationMs: number;
}

/** A scripted day-in-the-life loop covering every state and expression. */
export const DEMO_SCRIPT: readonly DemoStep[] = [
  { state: "idle", expression: "neutral", durationMs: 5000 },
  {
    state: "listening",
    expression: "curious",
    durationMs: 3000,
    caption: { who: "user", text: "What's on today?" },
  },
  { state: "thinking", expression: "neutral", durationMs: 2500 },
  {
    state: "speaking",
    expression: "happy",
    durationMs: 4500,
    caption: {
      who: "jarvis",
      text: "Stand-up at 9:30, then a clear afternoon.",
    },
  },
  {
    state: "listening",
    expression: "neutral",
    durationMs: 3000,
    caption: { who: "user", text: "Plan the print for the new enclosure." },
  },
  {
    state: "offloaded",
    expression: "curious",
    durationMs: 4000,
    caption: { who: "jarvis", text: "Give me a moment — I'll ping you." },
  },
  {
    state: "speaking",
    expression: "amused",
    durationMs: 4000,
    caption: {
      who: "jarvis",
      text: "Done. Eleven hours, so maybe start tonight.",
    },
  },
  {
    state: "speaking",
    expression: "concerned",
    durationMs: 4000,
    caption: { who: "jarvis", text: "Heads up: rain from three." },
  },
  { state: "idle", expression: "neutral", durationMs: 5000 },
  { state: "disconnected", expression: "neutral", durationMs: 3500 },
];

type Listener = () => void;

/**
 * Cycles through a script on a timer so the screens can be judged without a
 * voice loop. `advance()` (tap) jumps to the next step and restarts its timer.
 */
export class DemoDriver {
  private index = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running = false;
  private readonly listeners = new Set<Listener>();

  constructor(private readonly script: readonly DemoStep[] = DEMO_SCRIPT) {
    if (script.length === 0) throw new Error("demo script is empty");
  }

  readonly subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Current step (stable identity until it changes). */
  readonly getSnapshot = (): DemoStep => this.script[this.index]!;

  get isRunning(): boolean {
    return this.running;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.schedule();
  }

  stop(): void {
    this.running = false;
    clearTimeout(this.timer);
    this.timer = undefined;
  }

  /** Jump to the next step (wrapping) and restart the timer. */
  advance(): void {
    this.index = (this.index + 1) % this.script.length;
    for (const listener of this.listeners) listener();
    if (this.running) this.schedule();
  }

  private schedule(): void {
    clearTimeout(this.timer);
    this.timer = setTimeout(
      () => this.advance(),
      this.getSnapshot().durationMs,
    );
  }
}
