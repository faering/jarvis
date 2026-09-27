import {
  lazy,
  Suspense,
  useRef,
  useState,
  type ComponentType,
  type LazyExoticComponent,
  type PointerEvent,
} from "react";
import {
  describePresence,
  type Caption,
  type Presence,
} from "../presence/presence.ts";
import {
  SCREEN_IDS,
  SCREENS,
  type ScreenId,
  type ScreenProps,
} from "./catalogue.ts";
import { saveScreen, stepScreen, type KeyValueStore } from "./selection.ts";

// One lazy component per catalogue entry: a screen's code loads when first shown.
const LAZY_SCREENS = Object.fromEntries(
  SCREEN_IDS.map((id) => [id, lazy(SCREENS[id].load)]),
) as Record<ScreenId, LazyExoticComponent<ComponentType<ScreenProps>>>;

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

export interface ScreenHostProps {
  presence: Presence;
  initialScreen: ScreenId;
  store: KeyValueStore | null;
  demo: boolean;
  onDemoChange: (on: boolean) => void;
  /** Tap on the screen (advances the demo). */
  onTap: () => void;
  /** Seconds idle before the screen dims (burn-in / power). */
  dimAfterS?: number;
}

/**
 * Shows one screen from the catalogue, switched by swipe or the small control
 * bar; the choice is remembered. Only the shown screen is mounted.
 */
export function ScreenHost({
  presence,
  initialScreen,
  store,
  demo,
  onDemoChange,
  onTap,
  dimAfterS = 60,
}: ScreenHostProps) {
  const [screen, setScreen] = useState(initialScreen);
  const start = useRef<{ x: number; y: number } | null>(null);

  const choose = (next: ScreenId) => {
    setScreen(next);
    saveScreen(store, next);
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
      choose(stepScreen(screen, dx < 0 ? 1 : -1));
    } else if (Math.abs(dx) < TAP_PX && Math.abs(dy) < TAP_PX) {
      onTap();
    }
  };

  const { state, expression, caption } = presence;
  const Screen = LAZY_SCREENS[screen];
  const quiet = state === "idle" || state === "disconnected";
  return (
    <div
      className={`screen screen-${screen}${quiet ? " screen-quiet" : ""}`}
      data-state={state}
      data-expression={expression}
      style={{ ["--dim-after" as string]: `${dimAfterS}s` }}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={() => (start.current = null)}
    >
      <div className="screen-drift">
        <Suspense fallback={null}>
          <Screen presence={presence} />
        </Suspense>
        {caption && <CaptionStrip caption={caption} />}
      </div>
      <nav
        className="switcher"
        aria-label="Screens"
        onPointerDown={(e) => e.stopPropagation()}
        onPointerUp={(e) => e.stopPropagation()}
      >
        {SCREEN_IDS.map((id) => (
          <button
            key={id}
            type="button"
            aria-pressed={id === screen}
            onClick={() => choose(id)}
          >
            {SCREENS[id].name}
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
