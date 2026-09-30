import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { logger } from "../log/logger.ts";

const log = logger("update");

/** The Rust side's event (src-tauri/src/update.rs); its payload is the installed version. */
export const UPDATE_EVENT = "update-installed";

/**
 * Call `onUpdate` with the installed version when the Rust side reports an update.
 * Returns an unlisten function. Outside Tauri (`pnpm dev`) there are no updates.
 */
export function onUpdateInstalled(
  onUpdate: (version: string) => void,
): () => void {
  if (!isTauri()) return () => {};
  let unlisten: (() => void) | null = null;
  let stopped = false;
  listen<string>(UPDATE_EVENT, (event) => {
    log.info("update installed", { version: event.payload });
    onUpdate(event.payload);
  })
    .then((off) => {
      if (stopped) off();
      else unlisten = off;
    })
    .catch((error: unknown) =>
      log.error("could not listen for updates", {}, { error }),
    );
  return () => {
    stopped = true;
    unlisten?.();
  };
}

/** Restart into the installed version (Rust `restart_app`). Never throws: a failure is logged. */
export async function restartApp(
  version: string,
  run: (cmd: string) => Promise<unknown> = invoke,
): Promise<void> {
  log.info("restarting for update", { version });
  try {
    await run("restart_app");
  } catch (error) {
    log.error("restart for update failed", { version }, { error });
  }
}
