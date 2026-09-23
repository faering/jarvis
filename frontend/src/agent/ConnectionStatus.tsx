import { useEffect, useState } from "react";
import type { AgentSnapshot } from "./client.ts";

/** Whole seconds until `until` (epoch ms), ticking while it is set. */
function useCountdown(until: number | null): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until === null) return;
    const tick = () => setNow(Date.now());
    const id = setInterval(tick, 250);
    tick();
    return () => clearInterval(id);
  }, [until]);
  return until === null ? null : Math.max(0, Math.ceil((until - now) / 1000));
}

function label(snapshot: AgentSnapshot, countdown: number | null): string {
  switch (snapshot.state) {
    case "connecting":
      return "Connecting…";
    case "open":
      return "Connected";
    case "reconnecting":
      return countdown ? `Reconnecting in ${countdown}s` : "Reconnecting…";
    case "incompatible":
      return `Incompatible agent (protocol ${snapshot.agentProtocol ?? "?"})`;
    case "closed":
      return "Disconnected";
  }
}

export interface ConnectionStatusProps {
  snapshot: AgentSnapshot;
  onRetry: () => void;
}

/** Pill showing the agent connection: state, agent version, retry countdown. */
export function ConnectionStatus({ snapshot, onRetry }: ConnectionStatusProps) {
  const countdown = useCountdown(snapshot.retryAt);
  const canRetry =
    snapshot.state === "incompatible" || snapshot.state === "closed";
  return (
    <div
      role="status"
      className={`connection connection-${snapshot.state}`}
      title={snapshot.lastError?.message}
    >
      <span className="connection-dot" aria-hidden="true" />
      <span>{label(snapshot, countdown)}</span>
      {snapshot.agentVersion && (
        <span className="connection-version">
          agent v{snapshot.agentVersion}
        </span>
      )}
      {canRetry && (
        <button type="button" className="connection-retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
