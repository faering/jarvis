import {
  formatAttrs,
  formatLine,
  parseLevel,
  severity,
  type Attributes,
  type Level,
  type LogRecord,
} from "./format.ts";
import { errorDetail } from "./stack.ts";

/**
 * The app's logger (docs/logging.md). `logger("agent.client").info("connected", {...})`.
 *
 * Every record goes to the console (formatted as the spec line) and, in the Tauri app,
 * to the Rust side through tauri-plugin-log, where one formatter writes stderr and the
 * daily file (`JARVIS_LOG_DIR`).
 *
 * Turn correlation: `setTurn(traceId)` when an agent frame carrying a trace id is
 * handled (`traceIdOf(payload)`); lines logged until the next turn change carry its
 * 8-char prefix. A single `opts.turn` overrides it.
 *
 * FATAL: `fatal()` logs, then terminates. In Tauri the Rust logger exits the process
 * (code 1) once the record is written; `fatal()` also throws a FatalError so the caller
 * stops right away (and, in the browser dev server, where there is no process to end).
 */

export interface LogOptions {
  /** An error to describe on ERROR/FATAL continuation lines (adds `error.type`). */
  error?: unknown;
  /** Trace id for this record instead of the current turn. */
  turn?: string | null;
}

export type LogFn = (
  message: string,
  attributes?: Attributes,
  opts?: LogOptions,
) => void;

export interface Logger {
  readonly name: string;
  trace: LogFn;
  debug: LogFn;
  info: LogFn;
  warn: LogFn;
  error: LogFn;
  /** Logs, then terminates the app (see the module comment). */
  fatal: (message: string, attributes?: Attributes, opts?: LogOptions) => never;
}

export type Sink = (record: LogRecord) => void;

export class FatalError extends Error {
  override name = "FatalError";
}

interface State {
  level: Level;
  sinks: Sink[];
  turn: string | null;
  now: () => Date;
}

const CONSOLE_METHOD: Record<Level, "debug" | "info" | "warn" | "error"> = {
  TRACE: "debug",
  DEBUG: "debug",
  INFO: "info",
  WARN: "warn",
  ERROR: "error",
  FATAL: "error",
};

/** Writes the formatted line to the console. */
export const consoleSink: Sink = (record) => {
  console[CONSOLE_METHOD[record.level]](formatLine(record));
};

type PluginLog = typeof import("@tauri-apps/plugin-log");

/**
 * Sends records to the Rust logger over the plugin's `log` command. Logger name, turn,
 * attributes (pre-formatted, so their order survives) and detail travel as key-values.
 */
export function tauriSink(
  load: () => Promise<PluginLog> = () => import("@tauri-apps/plugin-log"),
): Sink {
  const plugin = load();
  let failed = false;
  return (record) => {
    const keyValues: Record<string, string | undefined> = {
      logger: record.logger,
      turn: record.turn ?? undefined,
      attrs: record.attrs || undefined,
      detail: record.detail || undefined,
      severity: record.level === "FATAL" ? "FATAL" : undefined,
    };
    const { message } = record;
    plugin
      .then((p) => {
        const send = {
          TRACE: p.trace,
          DEBUG: p.debug,
          INFO: p.info,
          WARN: p.warn,
          ERROR: p.error,
          FATAL: p.error,
        }[record.level];
        return send(message, { keyValues });
      })
      .catch((err: unknown) => {
        if (failed) return;
        failed = true;
        console.error("log: cannot reach the Tauri log plugin", err);
      });
  };
}

declare global {
  /** Set by the Rust side from JARVIS_LOG_LEVEL (logging::level_plugin). */
  var __JARVIS_LOG_LEVEL__: string | undefined;
}

function inTauri(): boolean {
  return "__TAURI_INTERNALS__" in globalThis;
}

function defaultState(): State {
  const tauri = inTauri();
  const configured = tauri
    ? globalThis.__JARVIS_LOG_LEVEL__
    : import.meta.env.VITE_LOG_LEVEL;
  return {
    level:
      parseLevel(configured) ??
      (!tauri && import.meta.env.DEV ? "DEBUG" : "INFO"),
    sinks: tauri ? [consoleSink, tauriSink()] : [consoleSink],
    turn: null,
    now: () => new Date(),
  };
}

let state: State | undefined;
const current = (): State => (state ??= defaultState());

/** Override the level, sinks or clock (tests; `level` also at runtime). */
export function configureLogging(patch: Partial<Omit<State, "turn">>): void {
  state = { ...current(), ...patch };
}

/** Back to the defaults for this environment (tests). */
export function resetLogging(): void {
  state = undefined;
}

/** The turn (trace id) of the agent frame being handled; null outside a turn. */
export function setTurn(traceId: string | null): void {
  current().turn = traceId;
}

export function currentTurn(): string | null {
  return current().turn;
}

function emit(
  name: string,
  level: Level,
  message: string,
  attributes: Attributes | undefined,
  opts: LogOptions | undefined,
  callerStack: string | undefined,
): void {
  const s = current();
  if (severity(level) < severity(s.level)) return;
  let attrs = attributes;
  let detail = "";
  if (severity(level) >= severity("ERROR")) {
    const err = opts?.error;
    if (err instanceof Error && !attrs?.["error.type"]) {
      attrs = { ...attrs, "error.type": err.name };
    }
    detail = errorDetail(err, callerStack);
  }
  const record: LogRecord = {
    time: s.now(),
    level,
    logger: name,
    turn: opts && "turn" in opts ? (opts.turn ?? null) : s.turn,
    message,
    attrs: formatAttrs(attrs),
    detail,
  };
  for (const sink of s.sinks) {
    try {
      sink(record);
    } catch {
      // A broken sink must never break the caller.
    }
  }
}

/** A named logger; the name is the dotted `logger` slot (`presence`, `agent.client`). */
export function logger(name: string): Logger {
  const at =
    (level: Level): LogFn =>
    (message, attributes, opts) =>
      emit(name, level, message, attributes, opts, undefined);
  return {
    name,
    trace: at("TRACE"),
    debug: at("DEBUG"),
    info: at("INFO"),
    warn: at("WARN"),
    error(message, attributes, opts) {
      emit(name, "ERROR", message, attributes, opts, new Error().stack);
    },
    fatal(message, attributes, opts): never {
      emit(name, "FATAL", message, attributes, opts, new Error().stack);
      throw new FatalError(message);
    },
  };
}
