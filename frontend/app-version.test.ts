import { describe, expect, it } from "vitest";
import { resolveAppVersion } from "./app-version.ts";

const output =
  "CANONICAL=0.1.0+3.gabc1234.dirty\nDOCKER_TAG=0.1.0-3-gabc1234-dirty\nREVISION=abc\n";

describe("resolveAppVersion", () => {
  it("prefers an injected VITE_APP_VERSION", () => {
    expect(resolveAppVersion("1.2.3", () => output)).toBe("1.2.3");
  });

  it("falls back to CANONICAL from scripts/version.sh", () => {
    expect(resolveAppVersion(undefined, () => output)).toBe(
      "0.1.0+3.gabc1234.dirty",
    );
    expect(resolveAppVersion("", () => output)).toBe("0.1.0+3.gabc1234.dirty");
  });

  it('falls back to "dev" when the script fails or prints no CANONICAL', () => {
    const fail = () => {
      throw new Error("not a git repository");
    };
    expect(resolveAppVersion(undefined, fail)).toBe("dev");
    expect(resolveAppVersion(undefined, () => "")).toBe("dev");
  });

  it("resolves this checkout to a canonical version", () => {
    expect(resolveAppVersion(undefined)).toMatch(
      /^\d+\.\d+\.\d+(\+\d+\.g[0-9a-f]+(\.dirty)?)?$/,
    );
  });
});
