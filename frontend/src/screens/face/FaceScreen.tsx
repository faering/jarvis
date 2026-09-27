import type { CSSProperties } from "react";
import {
  describePresence,
  type Expression,
  type Presence,
  type PresenceState,
} from "../../presence/presence.ts";
import "./face.css";

// Pre-drawn looks: eyes open/gaze per loop state, brows + mouth per expression.
// Only transforms and opacity animate (cheap on the Pi); paths swap instantly.

const EYE_OPEN: Record<PresenceState, number> = {
  idle: 1,
  listening: 1.15,
  thinking: 0.7,
  speaking: 1,
  offloaded: 0.8,
  disconnected: 0.12,
};

const GAZE: Record<PresenceState, [number, number]> = {
  idle: [0, 0],
  listening: [0, 2],
  thinking: [-10, -8],
  speaking: [0, 0],
  offloaded: [10, -8],
  disconnected: [0, 6],
};

const EXPRESSION_EYE: Record<Expression, number> = {
  neutral: 1,
  happy: 0.75,
  curious: 1.05,
  concerned: 0.9,
  amused: 0.6,
};

const MOUTH: Record<Expression, string> = {
  neutral: "M100 132 Q120 136 140 132",
  happy: "M96 126 Q120 150 144 126",
  curious: "M114 134 a6 6 0 1 0 12 0 a6 6 0 1 0 -12 0",
  concerned: "M100 138 Q120 126 140 138",
  amused: "M98 130 Q126 148 146 124",
};

// Brows as [x1, y1, x2, y2] per eye (left, right), or none.
const BROWS: Partial<Record<Expression, [number[], number[]]>> = {
  curious: [
    [64, 30, 96, 30],
    [144, 38, 176, 40],
  ],
  concerned: [
    [64, 38, 96, 32],
    [144, 32, 176, 38],
  ],
};

function Eye({ cx, open }: { cx: number; open: number }) {
  return (
    <g transform={`translate(${cx} 70)`}>
      <g className="face-eye-open" style={{ transform: `scaleY(${open})` }}>
        <rect
          className="face-eye"
          x={-15}
          y={-22}
          width={30}
          height={44}
          rx={15}
        />
      </g>
    </g>
  );
}

export function FaceScreen({ presence }: { presence: Presence }) {
  const { state, expression } = presence;
  const open = EYE_OPEN[state] * EXPRESSION_EYE[expression];
  const [gx, gy] = GAZE[state];
  const brows = state === "disconnected" ? undefined : BROWS[expression];
  const gaze: CSSProperties = { transform: `translate(${gx}px, ${gy}px)` };

  return (
    <svg
      className="face"
      viewBox="0 0 240 180"
      role="img"
      aria-label={`Jarvis face: ${describePresence(presence)}`}
    >
      <g className="face-breathe">
        <g className="face-gaze" style={gaze}>
          <g className="face-blink">
            <Eye cx={80} open={open} />
            <Eye cx={160} open={open} />
          </g>
          {brows?.map(([x1, y1, x2, y2], i) => (
            <line key={i} className="face-brow" {...{ x1, y1, x2, y2 }} />
          ))}
        </g>
        {state === "speaking" ? (
          <ellipse
            className="face-mouth-talk"
            cx={120}
            cy={134}
            rx={16}
            ry={9}
          />
        ) : state === "disconnected" ? (
          <path className="face-mouth" d="M106 134 L134 134" />
        ) : (
          <path className="face-mouth" d={MOUTH[expression]} />
        )}
        {state === "thinking" && (
          <g className="face-dots" aria-hidden="true">
            <circle cx={196} cy={24} r={4} />
            <circle cx={208} cy={16} r={4} />
            <circle cx={220} cy={8} r={4} />
          </g>
        )}
        {state === "offloaded" && (
          <circle
            className="face-spinner"
            aria-hidden="true"
            cx={212}
            cy={22}
            r={10}
            strokeDasharray="16 48"
          />
        )}
      </g>
    </svg>
  );
}
