/** The default-screen prototypes being compared in spike #133. */
export const VARIANTS = ["face", "orb", "ambient"] as const;
export type Variant = (typeof VARIANTS)[number];

export const VARIANT_LABELS: Record<Variant, string> = {
  face: "Face",
  orb: "Orb",
  ambient: "Ambient",
};

export const VARIANT_STORAGE_KEY = "jarvis.screen";
export const DEMO_STORAGE_KEY = "jarvis.demo";

/** The slice of Web Storage we use; injectable for tests. */
export type KeyValueStore = Pick<Storage, "getItem" | "setItem">;

export function isVariant(value: unknown): value is Variant {
  return typeof value === "string" && VARIANTS.includes(value as Variant);
}

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
 * `VITE_DEFAULT_SCREEN` > face. Invalid values are skipped.
 */
export function initialVariant(
  search: string,
  store: KeyValueStore | null,
  envDefault: string | undefined,
): Variant {
  const candidates = [
    new URLSearchParams(search).get("screen"),
    read(store, VARIANT_STORAGE_KEY),
    envDefault,
  ];
  return candidates.find(isVariant) ?? "face";
}

export function saveVariant(store: KeyValueStore | null, variant: Variant) {
  write(store, VARIANT_STORAGE_KEY, variant);
}

/** The next/previous variant, wrapping (swipe and the switcher use this). */
export function stepVariant(current: Variant, delta: 1 | -1): Variant {
  const i = VARIANTS.indexOf(current);
  return VARIANTS[(i + delta + VARIANTS.length) % VARIANTS.length]!;
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
