import type { AgentClient } from "./agent/client.ts";
import { ConnectionStatus } from "./agent/ConnectionStatus.tsx";
import { useAgentConnection } from "./agent/useAgentConnection.ts";

const version: string = import.meta.env.VITE_APP_VERSION ?? "dev";

export function App({ agent }: { agent: AgentClient }) {
  const connection = useAgentConnection(agent);
  return (
    <div className="app">
      <header className="app-header">
        <h1>Jarvis</h1>
        <span className="app-version">v{version}</span>
        <ConnectionStatus snapshot={connection} onRetry={() => agent.retry()} />
      </header>
      <main className="app-main" />
    </div>
  );
}
