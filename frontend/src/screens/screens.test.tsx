import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  describePresence,
  EXPRESSIONS,
  PRESENCE_STATES,
  type Presence,
} from "../presence/presence.ts";
import { AmbientScreen } from "./AmbientScreen.tsx";
import { FaceScreen } from "./FaceScreen.tsx";
import { OrbScreen } from "./OrbScreen.tsx";
import { ScreenGallery } from "./ScreenGallery.tsx";
import { VARIANTS, type Variant } from "./variants.ts";

const presences: Presence[] = PRESENCE_STATES.flatMap((state) =>
  EXPRESSIONS.map((expression) => ({ state, expression })),
);

describe("variants render every presence", () => {
  it.each(presences)("face: $state/$expression", (presence) => {
    const html = renderToStaticMarkup(<FaceScreen presence={presence} />);
    expect(html).toContain('role="img"');
    expect(html).toContain(
      `aria-label="Jarvis face: ${describePresence(presence)}"`,
    );
  });

  it.each(presences)("orb: $state/$expression", (presence) => {
    const html = renderToStaticMarkup(<OrbScreen presence={presence} />);
    expect(html).toContain(
      `aria-label="Jarvis orb: ${describePresence(presence)}"`,
    );
  });

  it.each(presences)("ambient: $state/$expression", (presence) => {
    const html = renderToStaticMarkup(
      <AmbientScreen presence={presence} now={new Date(2026, 8, 27, 9, 5)} />,
    );
    expect(html).toContain('aria-label="Ambient dashboard"');
    expect(html).toContain("Next up");
    expect(html).toContain(
      `aria-label="Jarvis orb: ${describePresence(presence)}"`,
    );
  });

  it("face shows a talking mouth only while speaking", () => {
    const talks = (state: Presence["state"]) =>
      renderToStaticMarkup(
        <FaceScreen presence={{ state, expression: "neutral" }} />,
      ).includes("face-mouth-talk");
    expect(talks("speaking")).toBe(true);
    expect(talks("idle")).toBe(false);
  });
});

describe("ScreenGallery", () => {
  const render = (variant: Variant, presence: Presence) =>
    renderToStaticMarkup(
      <ScreenGallery
        presence={presence}
        initialVariant={variant}
        store={null}
        demo
        onDemoChange={() => {}}
        onTap={() => {}}
      />,
    );

  it.each(VARIANTS)("shows %s with the switcher", (variant) => {
    const html = render(variant, { state: "idle", expression: "neutral" });
    expect(html).toContain(`screen-${variant}`);
    expect(html).toContain('aria-label="Screen prototypes"');
    expect(html).toMatch(/aria-pressed="true">(Face|Orb|Ambient)</);
    expect(html).toContain("screen-quiet"); // idle may dim
  });

  it("shows the conversation overlay when there is a caption", () => {
    const html = render("face", {
      state: "speaking",
      expression: "happy",
      caption: { who: "jarvis", text: "Stand-up at 9:30." },
    });
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("Stand-up at 9:30.");
    expect(html).not.toContain("screen-quiet");
  });
});
