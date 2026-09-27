import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.tsx";
import { AgentClient, DEFAULT_AGENT_WS_URL } from "./agent/client.ts";
import { logger } from "./log/logger.ts";
import "./index.css";
import "./screens/screens.css";

const log = logger("ui");
log.info("ui started", { version: import.meta.env.VITE_APP_VERSION ?? "dev" });
globalThis.addEventListener("error", (event) =>
  log.error("uncaught error", undefined, {
    error: event.error ?? event.message,
  }),
);
globalThis.addEventListener("unhandledrejection", (event) =>
  log.error("unhandled rejection", undefined, { error: event.reason }),
);

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");

const agent = new AgentClient({
  url: import.meta.env.VITE_AGENT_WS_URL || DEFAULT_AGENT_WS_URL,
});
agent.start();

createRoot(root).render(
  <StrictMode>
    <App agent={agent} />
  </StrictMode>,
);
