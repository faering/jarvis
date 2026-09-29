import { useEffect, useState } from "react";
import type { Presence } from "../../presence/presence.ts";
import { OrbScreen } from "../orb/OrbScreen.tsx";
import "./ambient.css";

/** Current time, re-rendered every `intervalMs`. */
function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

const time = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
});
const day = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  day: "numeric",
  month: "long",
});

/**
 * Clock-first dashboard with the orb small in a corner. The cards are
 * placeholders until calendar/todos/weather (Faelab) reach the app.
 */
export function AmbientScreen({
  presence,
  now: fixedNow,
}: {
  presence: Presence;
  /** Fixed time for tests; otherwise a live clock. */
  now?: Date;
}) {
  const liveNow = useNow(10_000);
  const now = fixedNow ?? liveNow;
  return (
    <section className="ambient" aria-label="Ambient dashboard">
      <div className="ambient-clock">
        <time className="ambient-time" dateTime={now.toISOString()}>
          {time.format(now)}
        </time>
        <div className="ambient-date">{day.format(now)}</div>
      </div>
      <ul className="ambient-cards" aria-label="Today (placeholder data)">
        <li className="ambient-card">
          <span className="ambient-card-label">Next up</span>
          <span>09:30 Stand-up</span>
        </li>
        <li className="ambient-card">
          <span className="ambient-card-label">Top todo</span>
          <span>Print enclosure v2</span>
        </li>
        <li className="ambient-card">
          <span className="ambient-card-label">Weather</span>
          <span>14°, rain from 15:00</span>
        </li>
      </ul>
      <div className="ambient-orb">
        <OrbScreen presence={presence} small />
      </div>
    </section>
  );
}
