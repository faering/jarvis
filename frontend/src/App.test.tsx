import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App.tsx";
import { AgentClient } from "./agent/client.ts";

describe("App shell", () => {
  it("renders the header with a version and an empty main area", () => {
    const html = renderToStaticMarkup(<App agent={new AgentClient()} />);
    expect(html).toContain("<h1>Jarvis</h1>");
    expect(html).toMatch(/class="app-version">v[^<]+</);
    expect(html).toContain('<main class="app-main"></main>');
  });

  it("shows the connection status pill", () => {
    const html = renderToStaticMarkup(<App agent={new AgentClient()} />);
    expect(html).toContain('role="status"');
    expect(html).toContain("Disconnected");
  });
});
