import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  escapeMessage,
  formatAttrs,
  formatLine,
  formatTime,
  LEVELS,
  parseLevel,
  quoteValue,
  turnSlot,
  type LogRecord,
} from "./format.ts";

const FIXTURE = new URL("../../../docs/logging-examples.log", import.meta.url);

/** Records of the shared fixture (continuation lines kept with their record). */
function fixtureRecords(): string[] {
  const records: string[] = [];
  for (const line of readFileSync(FIXTURE, "utf8").split("\n")) {
    if (line.startsWith("[")) records.push(line);
    else if (line && records.length) records[records.length - 1] += `\n${line}`;
  }
  return records;
}

function record(patch: Partial<LogRecord>): LogRecord {
  return {
    time: new Date("2026-09-27T15:44:39.310Z"),
    level: "INFO",
    logger: "x",
    turn: null,
    message: "m",
    attrs: "",
    detail: "",
    ...patch,
  };
}

describe("formatLine", () => {
  it("reproduces the [app] lines of docs/logging-examples.log", () => {
    const app = fixtureRecords().filter((r) => r.includes("] [app] ["));
    expect(app).toHaveLength(2);
    expect([
      formatLine(
        record({
          logger: "presence",
          turn: "4bf92f3577b34da6a3ce929d0e0e4736",
          message: "state changed",
          attrs: formatAttrs({ state: "thinking" }),
        }),
      ),
      formatLine(
        record({
          time: new Date("2026-09-27T16:02:12.000Z"),
          level: "FATAL",
          logger: "main",
          message: "cannot start: display not found",
          detail: "at src-tauri/src/main.rs:42 in main",
        }),
      ),
    ]).toEqual(app);
  });

  it("formats the fixture's escaping edge case the same way", () => {
    const agentLine = fixtureRecords().find((r) => r.includes("reply ready"));
    const line = formatLine(
      record({
        time: new Date("2026-09-27T15:44:39.500Z"),
        turn: "4bf92f3577b34da6a3ce929d0e0e4736",
        logger: "routing",
        message: "reply ready\nsecond line kept on one line",
        attrs: formatAttrs({
          note: 'has "quotes" and a \\ backslash',
          empty: "",
        }),
      }),
    );
    // Same line, except the component slot.
    expect(line).toBe(agentLine?.replace("[agent]", "[app]"));
  });

  it("pads levels to five with OTel names", () => {
    expect(
      LEVELS.map((level) => formatLine(record({ level })).slice(27, 34)),
    ).toEqual([
      "[TRACE]",
      "[DEBUG]",
      "[INFO ]",
      "[WARN ]",
      "[ERROR]",
      "[FATAL]",
    ]);
  });

  it("indents continuation lines by four spaces", () => {
    expect(
      formatLine(
        record({ level: "ERROR", detail: "at a.ts:1 in f\nError: x\n  at g" }),
      ),
    ).toBe(
      "[2026-09-27 15:44:39.310Z] [ERROR] [app] [x] [--------] m\n    at a.ts:1 in f\n    Error: x\n      at g",
    );
  });
});

describe("parts", () => {
  it("formats UTC with millisecond precision", () => {
    expect(formatTime(new Date(Date.UTC(2026, 0, 2, 3, 4, 5, 6)))).toBe(
      "2026-01-02 03:04:05.006Z",
    );
  });

  it("quotes values with whitespace, = or quotes, and empty values", () => {
    expect(quoteValue("plain")).toBe("plain");
    expect(quoteValue("C:\\x")).toBe("C:\\x");
    expect(quoteValue("")).toBe('""');
    expect(quoteValue("a b")).toBe('"a b"');
    expect(quoteValue("a=b")).toBe('"a=b"');
    expect(quoteValue('say "hi" \\ bye')).toBe('"say \\"hi\\" \\\\ bye"');
    expect(quoteValue("two\nlines")).toBe('"two\\nlines"');
  });

  it("formats attributes in order and drops undefined", () => {
    expect(
      formatAttrs({ a: 1, b: true, c: undefined, d: null, "error.type": "E" }),
    ).toBe("a=1 b=true d=null error.type=E");
    expect(formatAttrs(undefined)).toBe("");
  });

  it("escapes newlines in the message", () => {
    expect(escapeMessage("a\nb\r\nc\rd")).toBe("a\\nb\\nc\\rd");
  });

  it("shows the first 8 hex chars of the turn or dashes", () => {
    expect(turnSlot("4bf92f3577b34da6a3ce929d0e0e4736")).toBe("4bf92f35");
    expect(turnSlot("nothex!!")).toBe("--------");
    expect(turnSlot(null)).toBe("--------");
  });

  it("parses configured levels", () => {
    expect(parseLevel("warning")).toBe("WARN");
    expect(parseLevel(" trace ")).toBe("TRACE");
    expect(parseLevel("critical")).toBe("FATAL");
    expect(parseLevel("loud")).toBeNull();
    expect(parseLevel(undefined)).toBeNull();
  });
});
