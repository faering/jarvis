import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.tsx";
import { AgentClient, DEFAULT_AGENT_WS_URL } from "./agent/client.ts";
import "./index.css";

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
