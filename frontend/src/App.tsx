import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentClient } from "./agent/client.ts";
import { ConnectionStatus } from "./agent/ConnectionStatus.tsx";
import { useAgentConnection } from "./agent/useAgentConnection.ts";
import { ChatInput } from "./conversation/ChatInput.tsx";
import { isTypingKey } from "./conversation/keys.ts";
import { useConversation } from "./conversation/useConversation.ts";
import { DemoDriver } from "./presence/demoDriver.ts";
import { usePresence } from "./presence/usePresence.ts";
import { ScreenHost } from "./screens/ScreenHost.tsx";
import {
  browserStore,
  initialDemo,
  initialScreen,
  saveDemo,
} from "./screens/selection.ts";
import { onUpdateInstalled, restartApp } from "./update/restart.ts";
import { RestartWhenQuiet } from "./update/restartWhenQuiet.ts";
import { bindWindowControls } from "./window/controls.ts";
import { minimizeWindow } from "./window/minimize.ts";

const version: string = import.meta.env.VITE_APP_VERSION ?? "dev";

export function App({ agent }: { agent: AgentClient }) {
  const connection = useAgentConnection(agent);
  const [boot] = useState(() => {
    const search = globalThis.location?.search ?? "";
    const store = browserStore();
    const dim = Number(new URLSearchParams(search).get("dim"));
    return {
      store,
      screen: initialScreen(search, store, import.meta.env.VITE_DEFAULT_SCREEN),
      demo: initialDemo(search, store, import.meta.env.DEV),
      dimAfterS: dim > 0 ? dim : undefined,
    };
  });
  const [driver] = useState(() => new DemoDriver());
  const [demo, setDemo] = useState(boot.demo);
  const { conversation, send } = useConversation(agent, connection.state);
  const presence = usePresence(connection, conversation, driver, demo);
  const connected = connection.state === "open";

  // The keyboard input: any printable key opens it (with that key typed); a tap
  // opens it empty. `n` remounts it per opening, so it starts from `initial`.
  const [typing, setTyping] = useState<{ initial: string; n: number } | null>(
    null,
  );
  const openings = useRef(0);
  const openInput = useCallback((initial: string) => {
    setTyping((open) => open ?? { initial, n: ++openings.current });
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!isTypingKey(e) || e.target instanceof HTMLInputElement) return;
      e.preventDefault();
      openInput(e.key);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [openInput]);
  // Minimize on the agent's command or Ctrl+M, also while typing (ADR 0013; the agent's
  // fixed-phrase trigger is an initial approach, #223).
  useEffect(
    () =>
      bindWindowControls({
        agent,
        target: globalThis,
        minimize: (source) => void minimizeWindow(source),
      }),
    [agent],
  );
  // A deploy installed a new version: restart into it once Jarvis is quiet (#183).
  // Created in the effect, so StrictMode's extra cleanup-and-rerun gets a fresh one.
  const restarter = useRef<RestartWhenQuiet | null>(null);
  useEffect(() => {
    const quiet = new RestartWhenQuiet((v) => void restartApp(v));
    restarter.current = quiet;
    const off = onUpdateInstalled((v) => quiet.updateInstalled(v));
    return () => {
      off();
      quiet.dispose();
      restarter.current = null;
    };
  }, []);
  const captions = presence.captions?.length ?? 0;
  useEffect(() => {
    restarter.current?.activity({
      state: presence.state,
      typing: typing !== null,
      captions,
    });
  }, [presence.state, typing, captions]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Jarvis</h1>
        <span className="app-version">v{version}</span>
        <ConnectionStatus snapshot={connection} onRetry={() => agent.retry()} />
      </header>
      <main className="app-main">
        <ScreenHost
          presence={presence}
          initialScreen={boot.screen}
          store={boot.store}
          demo={demo}
          onDemoChange={(on) => {
            setDemo(on);
            saveDemo(boot.store, on);
          }}
          onTap={() => (demo ? driver.advance() : openInput(""))}
          awake={typing !== null}
          input={
            typing && (
              <ChatInput
                key={typing.n}
                initial={typing.initial}
                enabled={connected}
                onSend={send}
                onClose={() => setTyping(null)}
              />
            )
          }
          dimAfterS={boot.dimAfterS}
        />
      </main>
    </div>
  );
}
