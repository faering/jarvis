import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AgentSnapshot } from "./client.ts";
import { ConnectionStatus } from "./ConnectionStatus.tsx";

const base: AgentSnapshot = {
  state: "open",
  agentVersion: "1.2.3",
  agentProtocol: 0,
  lastError: null,
  retryAt: null,
};

const render = (snapshot: Partial<AgentSnapshot>) =>
  renderToStaticMarkup(
    <ConnectionStatus snapshot={{ ...base, ...snapshot }} onRetry={() => {}} />,
  );

describe("ConnectionStatus", () => {
  it("shows the state and agent version when open", () => {
    const html = render({});
    expect(html).toContain("Connected");
    expect(html).toContain("agent v1.2.3");
    expect(html).not.toContain("Retry");
  });

  it("shows a retry countdown while reconnecting", () => {
    const html = render({ state: "reconnecting", retryAt: Date.now() + 3_000 });
    expect(html).toMatch(/Reconnecting in [23]s/);
  });

  it("offers a manual retry when incompatible", () => {
    const html = render({ state: "incompatible", agentProtocol: 1 });
    expect(html).toContain("Incompatible agent (protocol 1)");
    expect(html).toContain("Retry");
  });
});
