import { useEffect, useSyncExternalStore } from "react";
import type { AgentSnapshot } from "../agent/client.ts";
import type { DemoDriver } from "./demoDriver.ts";
import { resolvePresence, type Presence } from "./presence.ts";

/** Presence from the live connection, or from the demo driver while it runs. */
export function usePresence(
  connection: AgentSnapshot,
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
  return resolvePresence({
    connection: connection.state,
    demo: demo ? step : null,
  });
}
