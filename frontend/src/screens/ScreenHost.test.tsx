import { describe, expect, it } from "vitest";
import type { Presence } from "../presence/presence.ts";
import { SCREEN_IDS, SCREENS, type ScreenId } from "./catalogue.ts";
import { ScreenHost } from "./ScreenHost.tsx";
import { renderResolved } from "./testing.ts";

const render = (screen: ScreenId, presence: Presence) =>
  renderResolved(
    <ScreenHost
      presence={presence}
      initialScreen={screen}
      store={null}
      demo
      onDemoChange={() => {}}
      onTap={() => {}}
    />,
  );

// The aria-label each screen's root carries.
const LABEL: Record<ScreenId, string> = {
  face: "Jarvis face:",
  orb: "Jarvis orb:",
  ambient: "Ambient dashboard",
};

describe("ScreenHost", () => {
  it.each(SCREEN_IDS)("shows %s with the switcher", async (screen) => {
    const html = await render(screen, { state: "idle", expression: "neutral" });
    expect(html).toContain(`screen-${screen}`);
    expect(html).toContain(LABEL[screen]);
    expect(html).toContain('aria-label="Screens"');
    expect(html).toContain(`aria-pressed="true">${SCREENS[screen].name}<`);
    expect(html).toContain("screen-quiet"); // idle may dim
  });

  it("mounts only the shown screen", async () => {
    const html = await render("face", { state: "idle", expression: "neutral" });
    expect(html).not.toContain(LABEL.orb);
    expect(html).not.toContain(LABEL.ambient);
  });

  it("shows the conversation overlay when there is a caption", async () => {
    const html = await render("face", {
      state: "speaking",
      expression: "happy",
      captions: [
        { who: "user", text: "What's on today?" },
        { who: "jarvis", text: "Stand-up at 9:30.", streaming: true },
      ],
    });
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("What&#x27;s on today?");
    expect(html).toContain("Stand-up at 9:30.");
    expect(html).toContain("caption-streaming");
    expect(html).not.toContain("screen-quiet");
  });
});

describe("ScreenHost conversation", () => {
  const renderWith = (extra: object, presence: Presence) =>
    renderResolved(
      <ScreenHost
        presence={presence}
        initialScreen="orb"
        store={null}
        demo={false}
        onDemoChange={() => {}}
        onTap={() => {}}
        {...extra}
      />,
    );

  it("stays awake while a conversation shows or while typing", async () => {
    const idle = { state: "idle", expression: "neutral" } as const;
    expect(await renderWith({}, idle)).toContain("screen-quiet");
    const talking = {
      ...idle,
      captions: [{ who: "jarvis", text: "Hi." }],
    } as Presence;
    expect(await renderWith({}, talking)).not.toContain("screen-quiet");
    expect(await renderWith({ awake: true }, idle)).not.toContain(
      "screen-quiet",
    );
  });

  it("draws the input slot and marks degraded and failed replies", async () => {
    const html = await renderWith(
      { input: <div className="chat-input">typing</div> },
      {
        state: "idle",
        expression: "concerned",
        captions: [
          { who: "jarvis", text: "Local.", tone: "degraded" },
          { who: "jarvis", text: "No.", tone: "error" },
        ],
      },
    );
    expect(html).toContain('class="chat-input"');
    expect(html).toContain("answered by the local model");
    expect(html).toContain("caption-error");
  });
});
