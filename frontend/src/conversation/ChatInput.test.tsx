import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ChatInput } from "./ChatInput.tsx";
import { isTypingKey } from "./keys.ts";

const key = (
  k: string,
  mods: Partial<Record<"ctrlKey" | "metaKey" | "altKey", boolean>> = {},
) => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...mods,
});

describe("isTypingKey", () => {
  it("accepts printable keys", () => {
    for (const k of ["a", "Z", "?", "7", "ø"])
      expect(isTypingKey(key(k))).toBe(true);
  });

  it("rejects shortcuts, space, named keys and IME composition", () => {
    expect(isTypingKey(key("c", { ctrlKey: true }))).toBe(false);
    expect(isTypingKey(key("v", { metaKey: true }))).toBe(false);
    expect(isTypingKey(key("x", { altKey: true }))).toBe(false);
    expect(isTypingKey(key(" "))).toBe(false);
    expect(isTypingKey(key("Enter"))).toBe(false);
    expect(isTypingKey(key("Escape"))).toBe(false);
    expect(isTypingKey({ ...key("a"), isComposing: true })).toBe(false);
  });
});

describe("ChatInput", () => {
  const render = (enabled: boolean) =>
    renderToStaticMarkup(
      <ChatInput
        initial="W"
        enabled={enabled}
        onSend={() => true}
        onClose={() => {}}
      />,
    );

  it("starts with the key that opened it", () => {
    const html = render(true);
    expect(html).toContain('aria-label="Message to Jarvis"');
    expect(html).toContain('value="W"');
    expect(html).toContain("Say something to Jarvis");
  });

  it("says when Jarvis is not connected", () => {
    expect(render(false)).toContain("Jarvis is not connected");
  });
});
