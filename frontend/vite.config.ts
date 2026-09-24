import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { resolveAppVersion } from "./app-version.ts";

// Vite reads VITE_* from process.env after loading this file, so the resolved build
// provenance reaches import.meta.env.VITE_APP_VERSION in dev, build and tests alike.
process.env.VITE_APP_VERSION = resolveAppVersion(process.env.VITE_APP_VERSION);

// Tauri expects a fixed dev port and serves the built files from dist/.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    target: "es2023",
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}", "*.test.ts"],
  },
});
