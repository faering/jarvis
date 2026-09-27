// Vitest setup: keep test output clean; tests that assert on logs install their own sink.
import { configureLogging } from "./logger.ts";

configureLogging({ sinks: [] });
