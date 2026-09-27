import { useRef, useState, type PointerEvent } from "react";
import {
  describePresence,
  type Caption,
  type Presence,
} from "../presence/presence.ts";
import { AmbientScreen } from "./AmbientScreen.tsx";
import { FaceScreen } from "./FaceScreen.tsx";
import { OrbScreen } from "./OrbScreen.tsx";
import {
  saveVariant,
  stepVariant,
  VARIANT_LABELS,
  VARIANTS,
  type KeyValueStore,
  type Variant,
} from "./variants.ts";

const SWIPE_PX = 60;
const TAP_PX = 12;

/** Conversation overlay: the last heard/spoken line while talking. */
function CaptionStrip({ caption }: { caption: Caption }) {
  return (
    <p className={`caption caption-${caption.who}`} aria-live="polite">
      <span className="caption-who">
        {caption.who === "user" ? "You" : "Jarvis"}
      </span>
      {caption.text}
    </p>
  );
}

export interface ScreenGalleryProps {
  presence: Presence;
  initialVariant: Variant;
  store: KeyValueStore | null;
  demo: boolean;
  onDemoChange: (on: boolean) => void;
  /** Tap on the screen (advances the demo). */
  onTap: () => void;
  /** Seconds idle before the screen dims (burn-in / power). */
  dimAfterS?: number;
}

/**
 * Prototype gallery for spike #133: shows one default-screen variant, switched
 * by swipe or the small control bar; the choice is remembered.
 */
export function ScreenGallery({
  presence,
  initialVariant,
  store,
  demo,
  onDemoChange,
  onTap,
  dimAfterS = 60,
}: ScreenGalleryProps) {
  const [variant, setVariant] = useState(initialVariant);
  const start = useRef<{ x: number; y: number } | null>(null);

  const choose = (next: Variant) => {
    setVariant(next);
    saveVariant(store, next);
  };

  const onPointerDown = (e: PointerEvent) => {
    start.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = (e: PointerEvent) => {
    const from = start.current;
    start.current = null;
    if (!from) return;
    const dx = e.clientX - from.x;
    const dy = e.clientY - from.y;
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy)) {
      choose(stepVariant(variant, dx < 0 ? 1 : -1));
    } else if (Math.abs(dx) < TAP_PX && Math.abs(dy) < TAP_PX) {
      onTap();
    }
  };

  const { state, expression, caption } = presence;
  const quiet = state === "idle" || state === "disconnected";
  return (
    <div
      className={`screen screen-${variant}${quiet ? " screen-quiet" : ""}`}
      data-state={state}
      data-expression={expression}
      style={{ ["--dim-after" as string]: `${dimAfterS}s` }}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={() => (start.current = null)}
    >
      <div className="screen-drift">
        {variant === "face" && <FaceScreen presence={presence} />}
        {variant === "orb" && <OrbScreen presence={presence} />}
        {variant === "ambient" && <AmbientScreen presence={presence} />}
        {caption && <CaptionStrip caption={caption} />}
      </div>
      <nav
        className="switcher"
        aria-label="Screen prototypes"
        onPointerDown={(e) => e.stopPropagation()}
        onPointerUp={(e) => e.stopPropagation()}
      >
        {VARIANTS.map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={v === variant}
            onClick={() => choose(v)}
          >
            {VARIANT_LABELS[v]}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={demo}
          onClick={() => onDemoChange(!demo)}
        >
          Demo
        </button>
        <span className="switcher-state">{describePresence(presence)}</span>
      </nav>
    </div>
  );
}
