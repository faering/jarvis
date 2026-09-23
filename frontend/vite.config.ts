import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

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
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
