import { prerender } from "react-dom/static";
import type { ReactNode } from "react";
import {
  EXPRESSIONS,
  PRESENCE_STATES,
  type Presence,
} from "../presence/presence.ts";

/** Every loop state × expression, for "renders every presence" tests. */
export const ALL_PRESENCES: Presence[] = PRESENCE_STATES.flatMap((state) =>
  EXPRESSIONS.map((expression) => ({ state, expression })),
);

/** Static HTML after lazy screens (Suspense) have resolved. */
export async function renderResolved(node: ReactNode): Promise<string> {
  const { prelude } = await prerender(node);
  return new Response(prelude).text();
}
