import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App.tsx";
import { AgentClient } from "./agent/client.ts";

describe("App shell", () => {
  it("renders the header with a version and the default screen", () => {
    const html = renderToStaticMarkup(<App agent={new AgentClient()} />);
    expect(html).toContain("<h1>Jarvis</h1>");
    expect(html).toMatch(/class="app-version">v[^<]+</);
    expect(html).toContain('<main class="app-main">');
    expect(html).toContain('aria-label="Screen prototypes"');
    expect(html).toContain("Jarvis face:");
  });

  it("shows the connection status pill", () => {
    const html = renderToStaticMarkup(<App agent={new AgentClient()} />);
    expect(html).toContain('role="status"');
    expect(html).toContain("Disconnected");
  });
});
