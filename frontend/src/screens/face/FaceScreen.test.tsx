import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { describePresence, type Presence } from "../../presence/presence.ts";
import { ALL_PRESENCES } from "../testing.ts";
import { FaceScreen } from "./FaceScreen.tsx";

describe("FaceScreen", () => {
  it.each(ALL_PRESENCES)("renders $state/$expression", (presence) => {
    const html = renderToStaticMarkup(<FaceScreen presence={presence} />);
    expect(html).toContain('role="img"');
    expect(html).toContain(
      `aria-label="Jarvis face: ${describePresence(presence)}"`,
    );
  });

  it("shows a talking mouth only while speaking", () => {
    const talks = (state: Presence["state"]) =>
      renderToStaticMarkup(
        <FaceScreen presence={{ state, expression: "neutral" }} />,
      ).includes("face-mouth-talk");
    expect(talks("speaking")).toBe(true);
    expect(talks("idle")).toBe(false);
  });
});
