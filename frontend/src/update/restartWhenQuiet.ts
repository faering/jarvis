import type { PresenceState } from "../presence/presence.ts";

/** How long Jarvis must stay quiet before it restarts into an installed update. */
export const QUIET_MS = 10_000;

export interface Activity {
  state: PresenceState;
  /** The typing input is open. */
  typing: boolean;
  /** Captions still on screen (they expire once Jarvis is idle). */
  captions: number;
}

/**
 * Quiet: nobody is talking to Jarvis and nothing is on its way. `offloaded` counts as busy,
 * since a heavy reply is still coming.
 */
export function isQuiet({ state, typing, captions }: Activity): boolean {
  return (
    (state === "idle" || state === "disconnected") && !typing && captions === 0
  );
}

export interface Timers {
  set: (run: () => void, ms: number) => unknown;
  clear: (handle: unknown) => void;
}

const realTimers: Timers = {
  set: (run, ms) => setTimeout(run, ms),
  clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/**
 * Restart into an installed update (#183) once Jarvis has been quiet for `quietMs` in a
 * row: the Rust side reports the update, this picks the moment, `restart` performs it.
 */
export class RestartWhenQuiet {
  private update: string | null = null;
  private quiet = false;
  private timer: unknown = null;
  private done = false;

  constructor(
    private readonly restart: (version: string) => void,
    private readonly timers: Timers = realTimers,
    private readonly quietMs = QUIET_MS,
  ) {}

  /** The Rust side saw a new version installed. */
  updateInstalled(version: string): void {
    this.update = version;
    this.reschedule();
  }

  /** What Jarvis is doing now; call on every change. */
  activity(activity: Activity): void {
    this.quiet = isQuiet(activity);
    this.reschedule();
  }

  dispose(): void {
    this.stop();
    this.done = true;
  }

  private reschedule(): void {
    if (this.done || this.update === null || !this.quiet) {
      this.stop();
      return;
    }
    if (this.timer !== null) return; // already counting down
    const version = this.update;
    this.timer = this.timers.set(() => {
      this.timer = null;
      this.done = true;
      this.restart(version);
    }, this.quietMs);
  }

  private stop(): void {
    if (this.timer === null) return;
    this.timers.clear(this.timer);
    this.timer = null;
  }
}
