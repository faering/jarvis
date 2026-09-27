import type { Envelope } from "@jarvis/protocol";
import {
  applyFrame,
  EMPTY_CONVERSATION,
  expire,
  said,
  type Conversation,
} from "./conversation.ts";

type Listener = () => void;

export interface ConversationStoreOptions {
  /** How long captions stay after the last change, once Jarvis is idle. */
  ttlMs?: number;
  now?: () => number;
}

/**
 * Holds the conversation for React (useSyncExternalStore) and clears the
 * captions `ttlMs` after the last change, once the loop is idle.
 */
export class ConversationStore {
  private state: Conversation = EMPTY_CONVERSATION;
  private readonly listeners = new Set<Listener>();
  private readonly ttlMs: number;
  private readonly now: () => number;
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(options: ConversationStoreOptions = {}) {
    this.ttlMs = options.ttlMs ?? 20_000;
    this.now = options.now ?? Date.now;
  }

  readonly subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getSnapshot = (): Conversation => this.state;

  readonly apply = (frame: Envelope): void => {
    this.set(applyFrame(this.state, frame, this.now()));
  };

  said(text: string): void {
    this.set(said(this.state, text, this.now()));
  }

  /** The agent is gone: its loop state is unknown, the captions stay until they expire. */
  disconnected(): void {
    if (this.state.loop !== null) this.set({ ...this.state, loop: null });
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.listeners.clear();
  }

  private set(next: Conversation): void {
    if (next === this.state) return;
    this.state = next;
    for (const listener of this.listeners) listener();
    this.scheduleExpiry();
  }

  private scheduleExpiry(): void {
    clearTimeout(this.timer);
    const { user, jarvis, changedAt } = this.state;
    if (user === null && jarvis === null) return;
    const due = Math.max(0, changedAt + this.ttlMs - this.now());
    this.timer = setTimeout(
      () => this.set(expire(this.state, this.now(), this.ttlMs)),
      due,
    );
  }
}
