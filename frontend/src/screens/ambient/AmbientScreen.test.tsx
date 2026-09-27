import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { describePresence } from "../../presence/presence.ts";
import { ALL_PRESENCES } from "../testing.ts";
import { AmbientScreen } from "./AmbientScreen.tsx";

describe("AmbientScreen", () => {
  it.each(ALL_PRESENCES)("renders $state/$expression", (presence) => {
    const html = renderToStaticMarkup(
      <AmbientScreen presence={presence} now={new Date(2026, 8, 27, 9, 5)} />,
    );
    expect(html).toContain('aria-label="Ambient dashboard"');
    expect(html).toContain("Next up");
    expect(html).toContain(
      `aria-label="Jarvis orb: ${describePresence(presence)}"`,
    );
  });
});
