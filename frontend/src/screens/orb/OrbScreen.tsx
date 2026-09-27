import { describePresence, type Presence } from "../../presence/presence.ts";
import "./orb.css";

const BARS = [-24, -12, 0, 12, 24];

/**
 * Arc-reactor style presence: a core, a solid ring and a segmented ring that
 * pulse/rotate per state. The "glow" is stacked translucent circles, not a
 * filter, so it stays cheap on the Pi.
 */
export function OrbScreen({
  presence,
  small = false,
}: {
  presence: Presence;
  small?: boolean;
}) {
  const { state } = presence;
  const offline = state === "disconnected";
  return (
    <svg
      className={small ? "orb orb-small" : "orb"}
      viewBox="0 0 200 200"
      role="img"
      aria-label={`Jarvis orb: ${describePresence(presence)}`}
    >
      <defs>
        <radialGradient id={small ? "orb-core-s" : "orb-core"}>
          <stop offset="0%" className="orb-stop-inner" />
          <stop offset="100%" className="orb-stop-outer" />
        </radialGradient>
      </defs>
      <g className="orb-halo">
        <circle cx={100} cy={100} r={92} opacity={0.06} />
        <circle cx={100} cy={100} r={80} opacity={0.1} />
      </g>
      <g className="orb-segments">
        <circle
          cx={100}
          cy={100}
          r={72}
          strokeDasharray={offline ? "4 10" : "22 10"}
        />
      </g>
      <circle className="orb-ring" cx={100} cy={100} r={60} />
      <g className="orb-pulse">
        <circle
          className="orb-core"
          cx={100}
          cy={100}
          r={34}
          fill={`url(#${small ? "orb-core-s" : "orb-core"})`}
        />
      </g>
      {(state === "speaking" || state === "listening") && (
        <g className="orb-wave" aria-hidden="true">
          {BARS.map((dx, i) => (
            <rect
              key={dx}
              className="orb-bar"
              style={{ animationDelay: `${i * -0.12}s` }}
              x={100 + dx - 3}
              y={86}
              width={6}
              height={28}
              rx={3}
            />
          ))}
        </g>
      )}
      {state === "offloaded" && (
        <g className="orb-orbit" aria-hidden="true">
          <circle cx={100} cy={14} r={5} />
        </g>
      )}
    </svg>
  );
}
