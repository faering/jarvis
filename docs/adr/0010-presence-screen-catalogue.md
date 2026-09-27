# 0010. Presence screens: a catalogue, the face by default
Status: Accepted · Date: 2026-09-27

## Context
Spike #133 asked what the 4–5" screen shows by default. #138 prototyped three screens (face,
orb, ambient) and they were judged in the browser at the Pi's resolution. The screen's main
job is still to come: showing panels (weather, today, diagrams) on request or when relevant
(#143). The presence screen is what shows the rest of the time.

## Decision
- **Keep every screen; the face is the default.** The user switches by swipe or the switcher
  now, and by voice later (#144).
- **Screens are a catalogue.** `frontend/src/screens/catalogue.ts` lists each screen (id,
  name, description, lazy loader) and is the one overview of what exists; each screen lives
  in its own folder with its styles and tests. Adding a screen = a folder + one entry.
- **Only the shown screen is loaded and mounted**, so extra screens cost no CPU or memory
  until chosen. Shared motion, burn-in drift/dim and reduced-motion stay in `screens.css`.
- **Pi budget (ADR 0001) applies to every screen:** animate only `transform` and `opacity`,
  no blur or filters.
- **Emotion source is not decided here.** `expression` stays app-local (demo driver) until
  the persona (#136) and speech catalogue (#123) decide between rules and an LLM tag.

## Alternatives
- **Pick one screen, delete the others:** simplest, but loses options the user wants to
  switch between, for no measurable saving.
- **All screens in one file / always mounted:** harder to see what exists, and inactive
  screens would still animate.
- **A Markdown list of screens:** drifts from the code; the catalogue file is the doc.

## Consequences
- The agent learns the available screens from the app (planned for #144), never a
  hardcoded list.
- The prototype switcher bar and demo mode stay until voice switching lands (#144).
- The mix of idle vs active screens (#133 option 6) can be revisited as a catalogue entry.

## Revisit when
- A screen needs heavy rendering (WebGL, video), or the Slint spike (#100) changes the
  frontend stack.
