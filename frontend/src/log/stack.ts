/**
 * Continuation lines for ERROR/FATAL records (docs/logging.md): `at <file>:<line> in
 * <function>`, then the error and its stack. Parses V8 (`at fn (file:1:2)`) and
 * WebKit/JSC (`fn@file:1:2`, the Tauri webview on Linux) frames.
 */

export interface Frame {
  fn: string;
  file: string;
  line: number;
}

const V8 = /^\s*at (?:(.+?) \()?(.+?):(\d+):\d+\)?$/;
const JSC = /^(.*?)@(.+?):(\d+):\d+$/;

/** `http://127.0.0.1:5173/src/agent/client.ts?t=1` -> `src/agent/client.ts`. */
function shortFile(file: string): string {
  return file.replace(/^[a-z-]+:\/\/[^/]*\//i, "").replace(/[?#].*$/, "");
}

export function parseFrames(stack: string | undefined): Frame[] {
  const frames: Frame[] = [];
  for (const raw of (stack ?? "").split("\n")) {
    const m = V8.exec(raw) ?? JSC.exec(raw.trim());
    if (!m) continue;
    const [, fn, file, line] = m;
    frames.push({
      fn: fn || "<anonymous>",
      file: shortFile(file ?? "?"),
      line: Number(line),
    });
  }
  return frames;
}

function atLine(frame: Frame | undefined): string {
  return frame ? `at ${frame.file}:${frame.line} in ${frame.fn}` : "at ? in ?";
}

/**
 * Detail lines for an ERROR/FATAL record: where it was logged (the error's first frame
 * when there is one), then `Name: message` and the error's frames. `callerStack` is
 * captured inside the logging method, so its first frame (the method) is skipped.
 */
export function errorDetail(error: unknown, callerStack?: string): string {
  if (error instanceof Error) {
    const frames = parseFrames(error.stack);
    return [
      atLine(frames[0]),
      `${error.name}: ${error.message}`,
      ...frames.map((f) => `  at ${f.fn} (${f.file}:${f.line})`),
    ].join("\n");
  }
  const lines = [atLine(parseFrames(callerStack)[1])];
  if (error !== undefined) lines.push(String(error));
  return lines.join("\n");
}
