/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Canonical build version from scripts/version.sh (unset in plain `pnpm dev`). */
  readonly VITE_APP_VERSION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
