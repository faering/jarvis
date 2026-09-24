/**
 * Agent <-> app integration: the real AgentClient (Node's global WebSocket) against a live
 * agent. Skipped unless AGENT_WS_URL is set; CI's `integration` job starts the agent.
 *
 * Env:
 *   AGENT_WS_URL                 agent WebSocket, e.g. ws://127.0.0.1:8000/ws
 *                                (devcontainer: ws://agent:8000/ws over jarvis-net)
 *   AGENT_EXPECT_VERSION         optional: the version the agent must report in hello
 *   AGENT_EXPECT_INCOMPATIBLE=1  the pair speaks different protocols: assert the client
 *                                stops at `incompatible` instead of the happy path
 *   AGENT_CLIENT_MODULE          optional: path to another client.ts (e.g. a released app's)
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type * as ClientModule from "../src/agent/client.ts";

const url = process.env.AGENT_WS_URL;
const expectVersion = process.env.AGENT_EXPECT_VERSION || null;
const expectIncompatible = process.env.AGENT_EXPECT_INCOMPATIBLE === "1";
const clientModule = process.env.AGENT_CLIENT_MODULE
  ? path.resolve(process.env.AGENT_CLIENT_MODULE)
  : fileURLToPath(new URL("../src/agent/client.ts", import.meta.url));

const { AgentClient } = (await import(
  /* @vite-ignore */ clientModule
)) as typeof ClientModule;
type Client = InstanceType<typeof AgentClient>;
type Snapshot = ReturnType<Client["getSnapshot"]>;

interface Frame {
  v: number;
  type: string;
  id: string | null;
  payload: Record<string, unknown>;
}

const cleanup: (() => unknown)[] = [];
afterEach(async () => {
  for (const fn of cleanup.splice(0)) await fn();
});

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Resolve with the first snapshot matching `predicate`. */
function waitFor(
  client: Client,
  predicate: (s: Snapshot) => boolean,
  timeoutMs = 5_000,
): Promise<Snapshot> {
  return new Promise((resolve, reject) => {
    if (predicate(client.getSnapshot())) return resolve(client.getSnapshot());
    const timer = setTimeout(() => {
      unsubscribe();
      reject(new Error(`timeout; last state ${client.getSnapshot().state}`));
    }, timeoutMs);
    const unsubscribe = client.subscribe(() => {
      if (!predicate(client.getSnapshot())) return;
      clearTimeout(timer);
      unsubscribe();
      resolve(client.getSnapshot());
    });
  });
}

/** A real AgentClient whose sockets record every frame sent and received. */
function spyClient(options: ClientModule.AgentClientOptions = {}) {
  const sockets: WebSocket[] = [];
  const sent: string[] = [];
  const received: Frame[] = [];
  class SpyWebSocket extends WebSocket {
    constructor(target: string | URL, protocols?: string | string[]) {
      super(target, protocols);
      sockets.push(this);
      this.addEventListener("message", (event) => {
        received.push(JSON.parse(String(event.data)) as Frame);
      });
    }
    override send(data: Parameters<WebSocket["send"]>[0]): void {
      if (typeof data === "string") sent.push(data);
      super.send(data);
    }
  }
  const client = new AgentClient({ ...options, url, WebSocket: SpyWebSocket });
  cleanup.push(() => client.stop());
  return { client, sockets, sent, received };
}

/** Frame types this suite exchanges on a raw socket. The agent may also push events at
 * any time (e.g. the voice loop's `state` right after `hello`); those are ignored here. */
const RAW_TYPES = new Set(["hello", "error", "pong"]);

/** A plain WebSocket to the agent, for frames the AgentClient never sends. */
async function rawSocket() {
  const socket = new WebSocket(url!);
  const queue: Frame[] = [];
  const waiters: ((frame: Frame) => void)[] = [];
  socket.addEventListener("message", (event) => {
    const frame = JSON.parse(String(event.data)) as Frame;
    if (!RAW_TYPES.has(frame.type)) return;
    const waiter = waiters.shift();
    if (waiter) waiter(frame);
    else queue.push(frame);
  });
  cleanup.push(() => socket.close());
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  const next = (timeoutMs = 5_000): Promise<Frame> => {
    const queued = queue.shift();
    if (queued) return Promise.resolve(queued);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("no frame")), timeoutMs);
      waiters.push((frame) => {
        clearTimeout(timer);
        resolve(frame);
      });
    });
  };
  return { socket, next };
}

/** The agent's GET /version `version`, or null for agents that predate the endpoint. */
async function versionEndpoint(): Promise<string | null> {
  const base = url!.replace(/^ws/, "http").replace(/\/ws$/, "");
  const response = await fetch(`${base}/version`);
  if (response.status === 404) return null;
  expect(response.ok).toBe(true);
  return ((await response.json()) as { version: string }).version;
}

describe.runIf(url && !expectIncompatible)(
  "AgentClient against the agent",
  () => {
    it("opens after hello with the agent's version", async () => {
      const { client } = spyClient();
      client.start();
      const snap = await waitFor(client, (s) => s.state === "open");
      expect(snap.agentVersion).toEqual(expect.any(String));
      const reported = await versionEndpoint();
      if (reported !== null) expect(snap.agentVersion).toBe(reported);
      if (expectVersion !== null) expect(snap.agentVersion).toBe(expectVersion);
    });

    it("stays open through several ping/pong heartbeats", async () => {
      const { client, sockets, sent, received } = spyClient({
        heartbeatIntervalMs: 100,
        pongTimeoutMs: 2_000,
      });
      const states: string[] = [];
      client.subscribe(() => states.push(client.getSnapshot().state));
      client.start();
      await waitFor(client, (s) => s.state === "open");
      await sleep(1_000);

      expect(client.getSnapshot().state).toBe("open");
      expect(states).not.toContain("reconnecting");
      expect(sockets).toHaveLength(1);
      const pings = sent
        .map((raw) => JSON.parse(raw) as Frame)
        .filter((f) => f.type === "ping");
      expect(pings.length).toBeGreaterThanOrEqual(3);
      const pongIds = received
        .filter((f) => f.type === "pong")
        .map((f) => f.id);
      for (const ping of pings.slice(0, -1)) expect(pongIds).toContain(ping.id);
    });

    it("surfaces the agent's error frame for a bad frame and stays open", async () => {
      const { client, sockets } = spyClient();
      client.start();
      await waitFor(client, (s) => s.state === "open");
      // The client only sends valid frames, so inject one on its own socket.
      sockets[0]!.send("not json");
      const snap = await waitFor(client, (s) => s.lastError !== null);
      expect(snap.lastError?.code).toBe("bad_json");
      await sleep(200);
      expect(client.getSnapshot().state).toBe("open");
      expect(sockets).toHaveLength(1);
    });

    it("answers malformed frames with error frames, never a disconnect", async () => {
      const raw = await rawSocket();
      expect((await raw.next()).type).toBe("hello");

      raw.socket.send(JSON.stringify({ v: 0 }));
      const badEnvelope = await raw.next();
      expect(badEnvelope).toMatchObject({ v: 0, type: "error" });
      expect(badEnvelope.payload.code).toBe("bad_envelope");

      const bogus = {
        v: 0,
        type: "integration.no-such-type",
        id: "it-1",
        payload: {},
      };
      raw.socket.send(JSON.stringify(bogus));
      expect(await raw.next()).toMatchObject({
        v: 0,
        type: "error",
        id: "it-1",
        payload: { code: "unknown_type" },
      });

      raw.socket.send(
        JSON.stringify({ v: 0, type: "ping", id: "it-2", payload: {} }),
      );
      expect(await raw.next()).toEqual({
        v: 0,
        type: "pong",
        id: "it-2",
        payload: {},
      });
    });
  },
);

describe.runIf(url && expectIncompatible)(
  "AgentClient against an incompatible agent",
  () => {
    it("stops at incompatible and does not retry", async () => {
      const { client, sockets } = spyClient({ backoff: () => 50 });
      client.start();
      const snap = await waitFor(client, (s) => s.state === "incompatible");
      expect(snap.agentProtocol).not.toBeNull();
      if (expectVersion !== null) expect(snap.agentVersion).toBe(expectVersion);
      await sleep(500); // well past the backoff
      expect(sockets).toHaveLength(1);
      expect(client.getSnapshot().state).toBe("incompatible");
    });
  },
);
