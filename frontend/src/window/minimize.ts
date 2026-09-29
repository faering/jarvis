import { invoke as tauriInvoke, isTauri } from "@tauri-apps/api/core";
import { logger } from "../log/logger.ts";

const log = logger("window");

/** Who asked: the agent's `window.minimize` command, or Ctrl+M. The Rust side checks it. */
export type MinimizeSource = "agent" | "keyboard";

export type Invoke = (
  cmd: string,
  args: Record<string, unknown>,
) => Promise<unknown>;

/** The Tauri IPC, or null in a plain browser (`pnpm dev`) where there is no window to minimize. */
function defaultInvoke(): Invoke | null {
  return isTauri() ? tauriInvoke : null;
}

/**
 * Minimize the app's window through the Rust `minimize_window` command (ADR 0013); the
 * taskbar brings it back. Never throws: a failure is logged.
 */
export async function minimizeWindow(
  source: MinimizeSource,
  invoke: Invoke | null = defaultInvoke(),
): Promise<void> {
  if (!invoke) {
    log.debug("window minimize skipped: not in Tauri", { source });
    return;
  }
  try {
    await invoke("minimize_window", { source });
    log.info("window minimized", { source });
  } catch (error) {
    log.error("window minimize failed", { source }, { error });
  }
}
