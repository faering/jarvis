import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App.tsx";

describe("App shell", () => {
  it("renders the header with a version and an empty main area", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("<h1>Jarvis</h1>");
    expect(html).toMatch(/class="app-version">v[^<]+</);
    expect(html).toContain('<main class="app-main"></main>');
  });
});
