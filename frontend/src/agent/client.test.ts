import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import { WebSocketServer, type WebSocket as ServerSocket } from "ws";
import {
  AgentClient,
  type AgentClientOptions,
  type AgentSnapshot,
} from "./client.ts";

interface FakeAgentOptions {
  /** Protocol announced in hello; null sends no hello at all. */
  protocol?: number | null;
  /** Answer pings with a matching pong. */
  pong?: boolean;
}

/** A minimal stand-in for the Python agent's /ws endpoint. */
async function fakeAgent({ protocol = 0, pong = true }: FakeAgentOptions = {}) {
  const server = new WebSocketServer({ port: 0, host: "127.0.0.1" });
  await new Promise<void>((resolve) => server.once("listening", resolve));
  const sockets: ServerSocket[] = [];
  const received: unknown[] = [];
  server.on("connection", (socket) => {
    sockets.push(socket);
    if (protocol !== null) {
      socket.send(
        JSON.stringify({
          v: 0,
          type: "hello",
          id: null,
          payload: { protocol, agent: "1.2.3" },
        }),
      );
    }
    socket.on("message", (data) => {
      const frame = JSON.parse(String(data)) as { type: string; id: string };
      received.push(frame);
      if (frame.type === "ping" && pong) {
        socket.send(
          JSON.stringify({ v: 0, type: "pong", id: frame.id, payload: {} }),
        );
      }
    });
  });
  const { port } = server.address() as AddressInfo;
  return {
    url: `ws://127.0.0.1:${port}/ws`,
    sockets,
    received,
    close: () =>
      new Promise<void>((resolve) => {
        for (const client of server.clients) client.terminate();
        server.close(() => resolve());
      }),
  };
}

const fast: AgentClientOptions = {
  backoff: () => 20,
  helloTimeoutMs: 500,
  heartbeatIntervalMs: 40,
  pongTimeoutMs: 60,
};

/** Resolve with the first snapshot matching `predicate`. */
function waitFor(
  client: AgentClient,
  predicate: (s: AgentSnapshot) => boolean,
  timeoutMs = 2_000,
): Promise<AgentSnapshot> {
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const cleanup: (() => unknown)[] = [];
afterEach(async () => {
  for (const fn of cleanup.splice(0)) await fn();
});

async function setup(agent: FakeAgentOptions = {}, options = fast) {
  const server = await fakeAgent(agent);
  const client = new AgentClient({ ...options, url: server.url });
  cleanup.push(
    () => client.stop(),
    () => server.close(),
  );
  return { server, client };
}

describe("AgentClient", () => {
  it("opens after hello and exposes the agent version", async () => {
    const { client } = await setup();
    client.start();
    expect(client.getSnapshot().state).toBe("connecting");
    const snap = await waitFor(client, (s) => s.state === "open");
    expect(snap.agentVersion).toBe("1.2.3");
    expect(snap.agentProtocol).toBe(0);
  });

  it("sends v0 pings and stays open while pongs echo the id", async () => {
    const { client, server } = await setup();
    client.start();
    await waitFor(client, (s) => s.state === "open");
    await sleep(250); // several heartbeat + pong-timeout windows
    expect(client.getSnapshot().state).toBe("open");
    expect(server.sockets).toHaveLength(1);
    expect(server.received.length).toBeGreaterThanOrEqual(2);
    expect(server.received[0]).toEqual({
      v: 0,
      type: "ping",
      id: expect.any(String),
      payload: {},
    });
  });

  it("exposes error frames as lastError", async () => {
    const { client, server } = await setup();
    client.start();
    await waitFor(client, (s) => s.state === "open");
    server.sockets[0]!.send(
      JSON.stringify({
        v: 0,
        type: "error",
        id: "x",
        payload: { code: "unknown_type", message: "unknown type 'foo'" },
      }),
    );
    const snap = await waitFor(client, (s) => s.lastError !== null);
    expect(snap.lastError).toEqual({
      code: "unknown_type",
      message: "unknown type 'foo'",
    });
    expect(snap.state).toBe("open");
  });

  it("stops at incompatible on a protocol mismatch until retry()", async () => {
    const { client, server } = await setup({ protocol: 1 });
    client.start();
    const snap = await waitFor(client, (s) => s.state === "incompatible");
    expect(snap.agentProtocol).toBe(1);
    expect(snap.agentVersion).toBe("1.2.3");
    await sleep(200); // well past the 20ms backoff
    expect(server.sockets).toHaveLength(1);
    expect(client.getSnapshot().state).toBe("incompatible");

    client.retry();
    expect(client.getSnapshot().state).toBe("connecting");
    await waitFor(client, (s) => s.state === "incompatible");
    expect(server.sockets).toHaveLength(2);
  });

  it("reconnects after the server closes the connection", async () => {
    const { client, server } = await setup();
    client.start();
    await waitFor(client, (s) => s.state === "open");
    server.sockets[0]!.close();
    const waiting = await waitFor(client, (s) => s.state === "reconnecting");
    expect(waiting.retryAt).not.toBeNull();
    await waitFor(client, (s) => s.state === "open");
    expect(server.sockets).toHaveLength(2);
  });

  it("reconnects when a pong does not arrive in time", async () => {
    const { client, server } = await setup({ pong: false });
    client.start();
    await waitFor(client, (s) => s.state === "open");
    await waitFor(client, (s) => s.state === "reconnecting");
    await waitFor(client, (s) => s.state === "open");
    expect(server.sockets.length).toBeGreaterThanOrEqual(2);
  });

  it("reconnects when no hello arrives in time", async () => {
    const { client, server } = await setup(
      { protocol: null },
      { ...fast, helloTimeoutMs: 50 },
    );
    client.start();
    await waitFor(client, (s) => s.state === "reconnecting");
    await waitFor(client, () => server.sockets.length >= 2);
    expect(client.getSnapshot().state).not.toBe("open");
  });

  it("resets the backoff after a successful hello", async () => {
    const attempts: number[] = [];
    const { client, server } = await setup(
      {},
      {
        ...fast,
        backoff: (attempt) => {
          attempts.push(attempt);
          return 20;
        },
      },
    );
    client.start();
    await waitFor(client, (s) => s.state === "open");
    server.sockets[0]!.close();
    await waitFor(client, (s) => s.state === "reconnecting");
    await waitFor(client, (s) => s.state === "open");
    server.sockets[1]!.close();
    await waitFor(client, (s) => s.state === "reconnecting");
    expect(attempts).toEqual([0, 0]);
  });

  it("stop() closes and does not reconnect", async () => {
    const { client, server } = await setup();
    client.start();
    await waitFor(client, (s) => s.state === "open");
    client.stop();
    expect(client.getSnapshot().state).toBe("closed");
    await sleep(100);
    expect(server.sockets).toHaveLength(1);
    expect(client.getSnapshot().state).toBe("closed");
  });
});
