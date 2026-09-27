/**
 * The log line of docs/logging.md, for the browser console. The Tauri app's file is
 * written by the Rust formatter (src-tauri/src/logging/line.rs) from the same fields;
 * both are tested against docs/logging-examples.log.
 *
 *   [timestamp] [LEVEL] [app] [logger] [turn] message  key=value ...
 */

/** OTel severity names, lowest first. */
export const LEVELS = [
  "TRACE",
  "DEBUG",
  "INFO",
  "WARN",
  "ERROR",
  "FATAL",
] as const;
export type Level = (typeof LEVELS)[number];

export const COMPONENT = "app";
export const NO_TURN = "--------";

export type AttrValue = string | number | boolean | null | undefined;
export type Attributes = Readonly<Record<string, AttrValue>>;

/** One record; `attrs` and `detail` are already formatted. */
export interface LogRecord {
  time: Date;
  level: Level;
  logger: string;
  /** Trace id of the turn (32 hex), or null outside a turn. */
  turn: string | null;
  message: string;
  /** Formatted attributes (formatAttrs), "" for none. */
  attrs: string;
  /** Continuation lines (ERROR/FATAL), newline-separated, without the indent. */
  detail: string;
}

export function severity(level: Level): number {
  return LEVELS.indexOf(level);
}

/** Parse a configured level, case-insensitive (WARNING/CRITICAL accepted). */
export function parseLevel(text: string | undefined): Level | null {
  const upper = (text ?? "").trim().toUpperCase();
  if (upper === "WARNING") return "WARN";
  if (upper === "CRITICAL") return "FATAL";
  return (LEVELS as readonly string[]).includes(upper)
    ? (upper as Level)
    : null;
}

const pad2 = (n: number) => String(n).padStart(2, "0");

/** `2026-09-27 15:44:38.123Z` (UTC, millisecond precision). */
export function formatTime(time: Date): string {
  return (
    `${time.getUTCFullYear()}-${pad2(time.getUTCMonth() + 1)}-${pad2(time.getUTCDate())} ` +
    `${pad2(time.getUTCHours())}:${pad2(time.getUTCMinutes())}:${pad2(time.getUTCSeconds())}.` +
    `${String(time.getUTCMilliseconds()).padStart(3, "0")}Z`
  );
}

/** First 8 hex chars of the trace id, else `--------`. */
export function turnSlot(turn: string | null): string {
  const prefix = turn?.slice(0, 8) ?? "";
  return /^[0-9a-fA-F]{8}$/.test(prefix) ? prefix : NO_TURN;
}

/** Keep the message on one line: newlines become a literal `\n`. */
export function escapeMessage(message: string): string {
  return message
    .replaceAll("\r\n", "\\n")
    .replaceAll("\n", "\\n")
    .replaceAll("\r", "\\r");
}

/**
 * Quote a value that is empty or holds whitespace, `=` or `"`; escape `"`, `\` and
 * newlines inside the quotes. Other values stay as they are.
 */
export function quoteValue(value: string): string {
  if (value !== "" && !/[\s="]/u.test(value)) return value;
  const escaped = value
    .replaceAll("\\", "\\\\")
    .replaceAll('"', '\\"')
    .replaceAll("\n", "\\n")
    .replaceAll("\r", "\\r");
  return `"${escaped}"`;
}

/** `key=value` pairs in insertion order; undefined values are left out. */
export function formatAttrs(attrs: Attributes | undefined): string {
  if (!attrs) return "";
  return Object.entries(attrs)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}=${quoteValue(String(v))}`)
    .join(" ");
}

/** The record as text: one line plus indented continuation lines. */
export function formatLine(record: LogRecord): string {
  let line =
    `[${formatTime(record.time)}] [${record.level.padEnd(5)}] [${COMPONENT}] ` +
    `[${record.logger}] [${turnSlot(record.turn)}] ${escapeMessage(record.message)}`;
  if (record.attrs) line += `  ${record.attrs}`;
  for (const cont of record.detail.split("\n")) {
    if (cont) line += `\n    ${cont}`;
  }
  return line;
}
