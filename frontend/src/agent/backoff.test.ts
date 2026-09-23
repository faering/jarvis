import { describe, expect, it } from "vitest";
import { backoffDelay } from "./backoff.ts";

const max = () => 0.999999;

describe("backoffDelay", () => {
  it("doubles the ceiling from a 0.5s base", () => {
    expect(backoffDelay(0, { random: max })).toBe(499);
    expect(backoffDelay(1, { random: max })).toBe(999);
    expect(backoffDelay(3, { random: max })).toBe(3999);
  });

  it("caps at 10s", () => {
    expect(backoffDelay(5, { random: max })).toBe(9999);
    expect(backoffDelay(50, { random: max })).toBe(9999);
  });

  it("applies full jitter over [0, ceiling)", () => {
    expect(backoffDelay(4, { random: () => 0 })).toBe(0);
    expect(backoffDelay(4, { random: () => 0.5 })).toBe(4000);
  });

  it("honours custom base and cap", () => {
    expect(backoffDelay(2, { baseMs: 10, capMs: 25, random: max })).toBe(24);
  });
});
