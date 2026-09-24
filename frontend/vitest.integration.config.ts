import { defineConfig } from "vitest/config";

// Agent <-> app integration suite: the real AgentClient against a live agent. Kept out of
// vite.config.ts's include so `turbo run test` stays offline. Run it with
// `AGENT_WS_URL=ws://127.0.0.1:8000/ws pnpm --dir frontend test:integration`.
export default defineConfig({
  test: {
    environment: "node",
    include: ["integration/**/*.test.ts"],
    testTimeout: 15_000,
  },
});
