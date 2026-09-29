import type { AgentClient } from "../agent/client.ts";
import type { MinimizeSource } from "./minimize.ts";

type Key = Pick<
  KeyboardEvent,
  "key" | "ctrlKey" | "altKey" | "metaKey" | "shiftKey"
>;

/** Ctrl+M, and no other modifier. */
export function isMinimizeKey(e: Key): boolean {
  return (
    e.ctrlKey &&
    !e.altKey &&
    !e.metaKey &&
    !e.shiftKey &&
    e.key.toLowerCase() === "m"
  );
}

export interface WindowControls {
  agent: Pick<AgentClient, "onCommand">;
  /** Where keydown is listened for (the window; it also sees keys typed in the input). */
  target: EventTarget;
  minimize: (source: MinimizeSource) => void;
}

/**
 * Run the window commands the agent sends, and the matching local keys. Returns an
 * unbind function. ADR 0013: the agent decides, the app executes. The agent picks
 * commands from fixed phrases for now, an INITIAL APPROACH to revisit (#223). Ctrl+M is
 * the user acting directly, so it works without the agent.
 */
export function bindWindowControls({
  agent,
  target,
  minimize,
}: WindowControls): () => void {
  const offCommand = agent.onCommand((command) => {
    if (command.name === "window.minimize") minimize("agent");
  });
  const onKey = (e: Event) => {
    if (!isMinimizeKey(e as KeyboardEvent)) return;
    e.preventDefault();
    minimize("keyboard");
  };
  target.addEventListener("keydown", onKey);
  return () => {
    offCommand();
    target.removeEventListener("keydown", onKey);
  };
}
