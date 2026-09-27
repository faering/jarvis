/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Canonical build version from scripts/version.sh (unset in plain `pnpm dev`). */
  readonly VITE_APP_VERSION?: string;
  /** Agent WebSocket URL; defaults to ws://127.0.0.1:8000/ws. */
  readonly VITE_AGENT_WS_URL?: string;
  /** Log level in the browser dev server (TRACE..FATAL); default DEBUG in dev, else INFO. */
  readonly VITE_LOG_LEVEL?: string;
  /** Default-screen prototype to show first: face | orb | ambient (spike #133). */
  readonly VITE_DEFAULT_SCREEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
