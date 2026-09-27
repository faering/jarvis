import type { ComponentType } from "react";
import type { Presence } from "../presence/presence.ts";

/**
 * Screen catalogue: every presence screen Jarvis can show, in one place.
 *
 * Each screen lives in its own folder (component + styles) and is loaded only
 * when first shown, so screens that aren't on display cost nothing at runtime.
 * To add one: create `screens/<id>/`, then add an entry here.
 */

export interface ScreenProps {
  presence: Presence;
}

export interface ScreenEntry {
  name: string;
  description: string;
  load: () => Promise<{ default: ComponentType<ScreenProps> }>;
}

export const SCREENS = {
  face: {
    name: "Face",
    description:
      "Eyes and a mouth: gaze and openness follow the loop state, brows and mouth the expression.",
    load: () =>
      import("./face/FaceScreen.tsx").then((m) => ({ default: m.FaceScreen })),
  },
  orb: {
    name: "Orb",
    description:
      "Arc-reactor core whose pulse and spin follow the loop state; waveform while listening or speaking.",
    load: () =>
      import("./orb/OrbScreen.tsx").then((m) => ({ default: m.OrbScreen })),
  },
  ambient: {
    name: "Ambient",
    description:
      "Clock, date and today's cards (next up, top todo, weather) with a small orb.",
    load: () =>
      import("./ambient/AmbientScreen.tsx").then((m) => ({
        default: m.AmbientScreen,
      })),
  },
} as const satisfies Record<string, ScreenEntry>;

export type ScreenId = keyof typeof SCREENS;

/** Catalogue order: the switcher and swipe follow it. */
export const SCREEN_IDS = Object.keys(SCREENS) as ScreenId[];

/** What Jarvis shows unless told otherwise (ADR 0010). */
export const DEFAULT_SCREEN: ScreenId = "face";

export function isScreenId(value: unknown): value is ScreenId {
  return typeof value === "string" && Object.hasOwn(SCREENS, value);
}
