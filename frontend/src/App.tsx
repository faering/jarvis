import { useState } from "react";
import type { AgentClient } from "./agent/client.ts";
import { ConnectionStatus } from "./agent/ConnectionStatus.tsx";
import { useAgentConnection } from "./agent/useAgentConnection.ts";
import { DemoDriver } from "./presence/demoDriver.ts";
import { usePresence } from "./presence/usePresence.ts";
import { ScreenGallery } from "./screens/ScreenGallery.tsx";
import {
  browserStore,
  initialDemo,
  initialVariant,
  saveDemo,
} from "./screens/variants.ts";

const version: string = import.meta.env.VITE_APP_VERSION ?? "dev";

export function App({ agent }: { agent: AgentClient }) {
  const connection = useAgentConnection(agent);
  const [boot] = useState(() => {
    const search = globalThis.location?.search ?? "";
    const store = browserStore();
    const dim = Number(new URLSearchParams(search).get("dim"));
    return {
      store,
      variant: initialVariant(
        search,
        store,
        import.meta.env.VITE_DEFAULT_SCREEN,
      ),
      demo: initialDemo(search, store),
      dimAfterS: dim > 0 ? dim : undefined,
    };
  });
  const [driver] = useState(() => new DemoDriver());
  const [demo, setDemo] = useState(boot.demo);
  const presence = usePresence(connection, driver, demo);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Jarvis</h1>
        <span className="app-version">v{version}</span>
        <ConnectionStatus snapshot={connection} onRetry={() => agent.retry()} />
      </header>
      <main className="app-main">
        <ScreenGallery
          presence={presence}
          initialVariant={boot.variant}
          store={boot.store}
          demo={demo}
          onDemoChange={(on) => {
            setDemo(on);
            saveDemo(boot.store, on);
          }}
          onTap={() => demo && driver.advance()}
          dimAfterS={boot.dimAfterS}
        />
      </main>
    </div>
  );
}
