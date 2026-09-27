import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LogRecord } from "./format.ts";
import {
  configureLogging,
  FatalError,
  logger,
  setTurn,
  tauriSink,
} from "./logger.ts";
import { errorDetail, parseFrames } from "./stack.ts";

const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";
let records: LogRecord[] = [];

beforeEach(() => {
  records = [];
  configureLogging({
    level: "TRACE",
    sinks: [(r) => records.push(r)],
    now: () => new Date("2026-09-27T15:44:39.310Z"),
  });
  setTurn(null);
});

afterEach(() => {
  configureLogging({ sinks: [] });
});

describe("logger", () => {
  it("drops records below the configured level", () => {
    configureLogging({ level: "INFO" });
    const log = logger("presence");
    log.trace("t");
    log.debug("d");
    log.info("i", { state: "idle" });
    log.warn("w");
    expect(records.map((r) => [r.level, r.logger, r.message, r.attrs])).toEqual(
      [
        ["INFO", "presence", "i", "state=idle"],
        ["WARN", "presence", "w", ""],
      ],
    );
  });

  it("stamps the current turn, which an option overrides", () => {
    const log = logger("presence");
    setTurn(TRACE_ID);
    log.info("in turn");
    log.info("explicit", undefined, { turn: null });
    setTurn(null);
    log.info("after");
    expect(records.map((r) => r.turn)).toEqual([TRACE_ID, null, null]);
  });

  it("describes errors on continuation lines and adds error.type", () => {
    const err = new TypeError("boom");
    logger("agent.client").error("failed", { code: 1 }, { error: err });
    const [r] = records;
    expect(r?.attrs).toBe("code=1 error.type=TypeError");
    const lines = r?.detail.split("\n") ?? [];
    expect(lines[0]).toMatch(/^at \S*src\/log\/logger\.test\.ts:\d+ in /);
    expect(lines[1]).toBe("TypeError: boom");
  });

  it("locates the caller of error() without an Error", () => {
    function caller() {
      logger("x").error("no error object");
    }
    caller();
    expect(records[0]?.detail).toMatch(
      /^at \S*src\/log\/logger\.test\.ts:\d+ in caller$/,
    );
  });

  it("fatal() logs FATAL, then throws so the caller stops", () => {
    expect(() => logger("main").fatal("cannot start")).toThrow(FatalError);
    expect(records[0]?.level).toBe("FATAL");
  });

  it("a failing sink never breaks the caller", () => {
    configureLogging({
      sinks: [
        () => {
          throw new Error("sink down");
        },
        (r) => records.push(r),
      ],
    });
    logger("x").info("still logged");
    expect(records).toHaveLength(1);
  });
});

describe("tauriSink", () => {
  it("sends logger, turn, attributes, detail and FATAL as key-values", async () => {
    const info = vi.fn(() => Promise.resolve());
    const error = vi.fn(() => Promise.resolve());
    const noop = () => Promise.resolve();
    const plugin = { trace: noop, debug: noop, warn: noop, info, error };
    const sink = tauriSink(() =>
      Promise.resolve(
        plugin as unknown as typeof import("@tauri-apps/plugin-log"),
      ),
    );
    configureLogging({ sinks: [sink] });
    setTurn(TRACE_ID);
    logger("presence").info("state changed", { state: "thinking" });
    setTurn(null);
    expect(() => logger("main").fatal("gone")).toThrow(FatalError);
    await vi.waitFor(() => expect(error).toHaveBeenCalled());

    expect(info).toHaveBeenCalledWith("state changed", {
      keyValues: {
        logger: "presence",
        turn: TRACE_ID,
        attrs: "state=thinking",
        detail: undefined,
        severity: undefined,
      },
    });
    expect(error).toHaveBeenCalledWith("gone", {
      keyValues: expect.objectContaining({
        logger: "main",
        severity: "FATAL",
        turn: undefined,
      }) as unknown,
    });
  });
});

describe("stack", () => {
  it("parses V8 and WebKit frames and shortens URLs", () => {
    const v8 = [
      "Error: x",
      "    at connect (http://127.0.0.1:5173/src/agent/client.ts?t=1:10:5)",
      "    at http://tauri.localhost/assets/index-abc.js:1:200",
    ].join("\n");
    const jsc = [
      "connect@tauri://localhost/assets/index-abc.js:3:7",
      "@tauri://localhost/assets/index-abc.js:4:1",
    ].join("\n");
    expect(parseFrames(v8)).toEqual([
      { fn: "connect", file: "src/agent/client.ts", line: 10 },
      { fn: "<anonymous>", file: "assets/index-abc.js", line: 1 },
    ]);
    expect(parseFrames(jsc)).toEqual([
      { fn: "connect", file: "assets/index-abc.js", line: 3 },
      { fn: "<anonymous>", file: "assets/index-abc.js", line: 4 },
    ]);
  });

  it("falls back when nothing is known", () => {
    expect(errorDetail(undefined, undefined)).toBe("at ? in ?");
    expect(errorDetail("text", undefined)).toBe("at ? in ?\ntext");
  });
});
