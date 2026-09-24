import { backoffDelay } from "./backoff.ts";
import {
  asError,
  asHello,
  envelope,
  parseEnvelope,
  PROTOCOL_VERSION,
  type Envelope,
  type ErrorPayload,
} from "@jarvis/protocol";

export const DEFAULT_AGENT_WS_URL = "ws://127.0.0.1:8000/ws";

export type ConnectionState =
  | "connecting" // first attempt, waiting for hello
  | "open" // hello received, protocol compatible
  | "reconnecting" // lost the connection; waiting for / attempting the next try
  | "incompatible" // agent speaks another protocol; retrying stops until retry()
  | "closed"; // stopped (or never started)

export interface AgentSnapshot {
  state: ConnectionState;
  /** Agent build version from hello (kept while reconnecting). */
  agentVersion: string | null;
  /** Protocol version the agent announced in its last hello. */
  agentProtocol: number | null;
  /** Payload of the last `error` frame from the agent. */
  lastError: ErrorPayload | null;
  /** Epoch ms of the next reconnect attempt while waiting, else null. */
  retryAt: number | null;
}

export interface AgentClientOptions {
  url?: string;
  /** WebSocket implementation; defaults to the global one. */
  WebSocket?: typeof WebSocket;
  /** Delay (ms) before reconnect attempt `attempt` (0-based). */
  backoff?: (attempt: number) => number;
  helloTimeoutMs?: number;
  heartbeatIntervalMs?: number;
  pongTimeoutMs?: number;
  now?: () => number;
}

type Listener = () => void;

/**
 * Framework-free client for the agent WebSocket bridge. Reconnects with
 * jittered backoff, checks the protocol in the agent's hello, and keeps the
 * link alive with ping/pong. Exposes an immutable snapshot for
 * useSyncExternalStore.
 */
export class AgentClient {
  private readonly url: string;
  private readonly WS: typeof WebSocket;
  private readonly backoff: (attempt: number) => number;
  private readonly helloTimeoutMs: number;
  private readonly heartbeatIntervalMs: number;
  private readonly pongTimeoutMs: number;
  private readonly now: () => number;

  private snapshot: AgentSnapshot = {
    state: "closed",
    agentVersion: null,
    agentProtocol: null,
    lastError: null,
    retryAt: null,
  };
  private readonly listeners = new Set<Listener>();
  private socket: WebSocket | null = null;
  private attempt = 0;
  private pingSeq = 0;
  private pendingPing: string | null = null;
  private helloTimer: ReturnType<typeof setTimeout> | undefined;
  private heartbeatTimer: ReturnType<typeof setTimeout> | undefined;
  private pongTimer: ReturnType<typeof setTimeout> | undefined;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(options: AgentClientOptions = {}) {
    this.url = options.url ?? DEFAULT_AGENT_WS_URL;
    this.WS = options.WebSocket ?? globalThis.WebSocket;
    this.backoff = options.backoff ?? ((attempt) => backoffDelay(attempt));
    this.helloTimeoutMs = options.helloTimeoutMs ?? 5_000;
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 15_000;
    this.pongTimeoutMs = options.pongTimeoutMs ?? 5_000;
    this.now = options.now ?? Date.now;
  }

  // Arrow properties: stable identities for useSyncExternalStore.
  readonly subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getSnapshot = (): AgentSnapshot => this.snapshot;

  /** Connect (no-op unless closed). */
  start(): void {
    if (this.snapshot.state !== "closed") return;
    this.attempt = 0;
    this.connect("connecting");
  }

  /** Disconnect and stop reconnecting. */
  stop(): void {
    this.teardown();
    this.update({ state: "closed", retryAt: null });
  }

  /** Manual retry, e.g. after `incompatible`: reconnect now, backoff reset. */
  retry(): void {
    this.teardown();
    this.attempt = 0;
    this.connect("connecting");
  }

  private connect(state: "connecting" | "reconnecting"): void {
    this.update({ state, retryAt: null });
    const socket = new this.WS(this.url);
    this.socket = socket;
    socket.onmessage = (event: MessageEvent) => {
      if (typeof event.data === "string") this.onFrame(event.data);
    };
    socket.onclose = () => this.reconnect();
    socket.onerror = () => {}; // a close event always follows
    // Covers both a hanging connect and a silent agent.
    this.helloTimer = setTimeout(() => this.reconnect(), this.helloTimeoutMs);
  }

  private onFrame(raw: string): void {
    const frame = parseEnvelope(raw);
    if (!frame) return;
    // Every frame carries the envelope version. hello goes through anyway so a mismatch
    // is reported as `incompatible`; any other frame from another version is ignored
    // (a foreign pong then lets the heartbeat time out and reconnect).
    if (frame.type !== "hello" && frame.v !== PROTOCOL_VERSION) return;
    switch (frame.type) {
      case "hello":
        this.onHello(frame);
        break;
      case "pong":
        if (frame.id !== null && frame.id === this.pendingPing) {
          this.pendingPing = null;
          clearTimeout(this.pongTimer);
          this.scheduleHeartbeat();
        }
        break;
      case "error":
        this.update({ lastError: asError(frame.payload) });
        break;
    }
  }

  private onHello(frame: Envelope): void {
    clearTimeout(this.helloTimer);
    const hello = asHello(frame.payload);
    const agentVersion = hello?.agent ?? null;
    const agentProtocol = hello?.protocol ?? null;
    // Both the envelope version and the announced protocol must match.
    if (
      frame.v !== PROTOCOL_VERSION ||
      !hello ||
      hello.protocol !== PROTOCOL_VERSION
    ) {
      this.teardown();
      this.update({ state: "incompatible", agentVersion, agentProtocol });
      return;
    }
    this.attempt = 0;
    this.update({ state: "open", agentVersion, agentProtocol, retryAt: null });
    this.scheduleHeartbeat();
  }

  private scheduleHeartbeat(): void {
    clearTimeout(this.heartbeatTimer);
    this.heartbeatTimer = setTimeout(() => {
      const id = `ping-${++this.pingSeq}`;
      this.pendingPing = id;
      this.send(envelope("ping", id));
      this.pongTimer = setTimeout(() => this.reconnect(), this.pongTimeoutMs);
    }, this.heartbeatIntervalMs);
  }

  private send(frame: Envelope): void {
    if (this.socket?.readyState === this.WS.OPEN) {
      this.socket.send(JSON.stringify(frame));
    }
  }

  /** Drop the current socket and schedule the next attempt. */
  private reconnect(): void {
    this.teardown();
    const delay = this.backoff(this.attempt++);
    this.update({ state: "reconnecting", retryAt: this.now() + delay });
    this.retryTimer = setTimeout(() => this.connect("reconnecting"), delay);
  }

  private teardown(): void {
    for (const timer of [
      this.helloTimer,
      this.heartbeatTimer,
      this.pongTimer,
      this.retryTimer,
    ]) {
      clearTimeout(timer);
    }
    this.pendingPing = null;
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onmessage = null;
      socket.onclose = null;
      socket.close();
    }
  }

  private update(patch: Partial<AgentSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener();
  }
}
