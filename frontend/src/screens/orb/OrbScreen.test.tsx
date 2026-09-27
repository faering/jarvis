import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { describePresence } from "../../presence/presence.ts";
import { ALL_PRESENCES } from "../testing.ts";
import { OrbScreen } from "./OrbScreen.tsx";

describe("OrbScreen", () => {
  it.each(ALL_PRESENCES)("renders $state/$expression", (presence) => {
    const html = renderToStaticMarkup(<OrbScreen presence={presence} />);
    expect(html).toContain(
      `aria-label="Jarvis orb: ${describePresence(presence)}"`,
    );
  });
});
