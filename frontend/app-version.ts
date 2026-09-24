// Build-time resolution of VITE_APP_VERSION (AGENTS.md "Build provenance & displayed
// versions"). CI sets it from scripts/version.sh; a plain local `pnpm dev`/`build` runs
// the script itself, so the header shows the same canonical string as the agent's GET
// /version. Runs in Node (vite.config.ts), never in the browser bundle.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const VERSION_SCRIPT = fileURLToPath(
  new URL("../scripts/version.sh", import.meta.url),
);

/** Returns scripts/version.sh output (KEY=VALUE lines); throws on failure. */
export type RunVersionScript = () => string;

const runVersionScript: RunVersionScript = () =>
  execFileSync(VERSION_SCRIPT, ["app"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });

/** The injected value if set, else CANONICAL from scripts/version.sh, else "dev". */
export function resolveAppVersion(
  injected: string | undefined,
  run: RunVersionScript = runVersionScript,
): string {
  if (injected) return injected;
  try {
    return /^CANONICAL=(.+)$/m.exec(run())?.[1] ?? "dev";
  } catch {
    return "dev"; // no git, no bash, or not a checkout (e.g. a source tarball)
  }
}
