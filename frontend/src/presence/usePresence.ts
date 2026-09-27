import { useEffect, useRef, useSyncExternalStore } from "react";
import type { AgentSnapshot } from "../agent/client.ts";
import { captionsOf, type Conversation } from "../conversation/conversation.ts";
import type { DemoDriver } from "./demoDriver.ts";
import { logger } from "../log/logger.ts";
import {
  resolvePresence,
  type Presence,
  type PresenceState,
} from "./presence.ts";

const log = logger("presence");

/** Presence from the agent (connection, loop state, conversation), or the demo driver. */
export function usePresence(
  connection: AgentSnapshot,
  conversation: Conversation,
  driver: DemoDriver,
  demo: boolean,
): Presence {
  const step = useSyncExternalStore(
    driver.subscribe,
    driver.getSnapshot,
    driver.getSnapshot,
  );
  useEffect(() => {
    if (!demo) return;
    driver.start();
    return () => driver.stop();
  }, [driver, demo]);
  const presence = resolvePresence({
    connection: connection.state,
    loop: conversation.loop,
    captions: captionsOf(conversation),
    demo: demo ? step : null,
  });
  // A ref, not the effect alone: StrictMode re-runs effects, the change is logged once.
  const logged = useRef<PresenceState | null>(null);
  useEffect(() => {
    if (logged.current === presence.state) return;
    logged.current = presence.state;
    log.info("state changed", {
      state: presence.state,
      demo: demo || undefined,
    });
  }, [presence.state, demo]);
  return presence;
}
