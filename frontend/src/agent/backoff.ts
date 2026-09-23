export interface BackoffOptions {
  baseMs?: number;
  capMs?: number;
  /** Uniform [0, 1); injectable for tests. */
  random?: () => number;
}

/**
 * Exponential backoff with full jitter: a uniform delay in
 * [0, min(cap, base * 2^attempt)). `attempt` starts at 0 and resets after a
 * successful hello.
 */
export function backoffDelay(
  attempt: number,
  { baseMs = 500, capMs = 10_000, random = Math.random }: BackoffOptions = {},
): number {
  const ceiling = Math.min(capMs, baseMs * 2 ** Math.max(0, attempt));
  return Math.floor(random() * ceiling);
}
