import {
  DEFAULT_SCREEN,
  isScreenId,
  SCREEN_IDS,
  type ScreenId,
} from "./catalogue.ts";

/** Which catalogue screen to show, and whether the demo driver runs. */

export const SCREEN_STORAGE_KEY = "jarvis.screen";
export const DEMO_STORAGE_KEY = "jarvis.demo";

/** The slice of Web Storage we use; injectable for tests. */
export type KeyValueStore = Pick<Storage, "getItem" | "setItem">;

function read(store: KeyValueStore | null, key: string): string | null {
  try {
    return store?.getItem(key) ?? null;
  } catch {
    return null; // storage can be blocked (private mode, quota)
  }
}

function write(store: KeyValueStore | null, key: string, value: string): void {
  try {
    store?.setItem(key, value);
  } catch {
    // best effort: the choice just isn't remembered
  }
}

/**
 * Pick the screen to show first: `?screen=` (explicit) > remembered choice >
 * `VITE_DEFAULT_SCREEN` > the catalogue default. Invalid values are skipped.
 */
export function initialScreen(
  search: string,
  store: KeyValueStore | null,
  envDefault: string | undefined,
): ScreenId {
  const candidates = [
    new URLSearchParams(search).get("screen"),
    read(store, SCREEN_STORAGE_KEY),
    envDefault,
  ];
  return candidates.find(isScreenId) ?? DEFAULT_SCREEN;
}

export function saveScreen(store: KeyValueStore | null, screen: ScreenId) {
  write(store, SCREEN_STORAGE_KEY, screen);
}

/** The next/previous screen in catalogue order, wrapping (swipe uses this). */
export function stepScreen(current: ScreenId, delta: 1 | -1): ScreenId {
  const i = SCREEN_IDS.indexOf(current);
  return SCREEN_IDS[(i + delta + SCREEN_IDS.length) % SCREEN_IDS.length]!;
}

/** Demo mode: `?demo=0|1` > remembered > on (no voice loop to drive it yet). */
export function initialDemo(search: string, store: KeyValueStore | null) {
  const value =
    new URLSearchParams(search).get("demo") ?? read(store, DEMO_STORAGE_KEY);
  return value !== "0";
}

export function saveDemo(store: KeyValueStore | null, on: boolean) {
  write(store, DEMO_STORAGE_KEY, on ? "1" : "0");
}

/** window.localStorage when available (it throws in some sandboxes). */
export function browserStore(): KeyValueStore | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}
