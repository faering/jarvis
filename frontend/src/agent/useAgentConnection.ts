import { useSyncExternalStore } from "react";
import type { AgentClient, AgentSnapshot } from "./client.ts";

/** Subscribe a component to the client's connection snapshot. */
export function useAgentConnection(client: AgentClient): AgentSnapshot {
  return useSyncExternalStore(
    client.subscribe,
    client.getSnapshot,
    client.getSnapshot,
  );
}
