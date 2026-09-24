# 0007. Layered config with profiles, probed hardware and capability manifests
Status: Accepted · Date: 2026-09-24

## Context
One agent image must run on the home Pi (Hailo + camera), the work Pi (voice only) and a
laptop (neither), and say what it can and cannot do (#63). Until now config was env-only
and scattered (`backends/config.py`, `store/config.py`).

## Decision
- **One pydantic schema** (`jarvis_agent.config`), layered, later wins: defaults → profile
  preset → local file (`JARVIS_CONFIG`) → env. Tables merge key by key; other values replace.
  All problems are collected into one `ConfigError`, each naming the layer it came from.
- **TOML via stdlib `tomllib`**; profiles ship as package data (`config/profiles/*.toml`),
  so they are in the wheel and the image with no Dockerfile change.
- **Existing env names keep working**: they map onto the schema, and the schema embeds
  `BackendSettings` / `StoreSettings` unchanged, so `build_backends()` / `open_state()` are
  untouched.
- **Hardware toggles `on|off|auto`**: `on`/`off` are trusted; `auto` runs a filesystem probe
  (`/dev/hailo0` or a Hailo PCI vendor id, an `imx500` V4L2 device, ALSA capture/playback
  PCMs, a connected DRM connector). Probes are injectable; no hardware libraries.
- **Capability manifests are Python dataclasses**: `requires` on hardware / backends / tools
  / state, plus providers (`local` or `faelab`, each on a routing `ComputeLayer`) with their
  own requirements. The resolver picks the first satisfiable provider in `prefer` order (an
  ordered allow-list; empty = manifest order). Unsatisfiable → disabled with a reason;
  configured `on` but unsatisfiable → also flagged `required`. Unknown names in config are
  config errors.

## Alternatives
- **YAML profiles:** rejected. Needs a new dependency; `tomllib` is stdlib.
- **pydantic-settings:** rejected. A new dependency, and it can't report which layer a bad
  value came from.
- **Rewriting backends/store config onto the new schema:** rejected. Embedding their models
  gives the same result with no churn and identical env behaviour.
- **Manifests as TOML files:** rejected for now. Dataclasses are type-checked and need no
  parser; MCP-discovered capabilities (#68) can build the same objects.
- **Reusing `routing.pick()` for providers:** rejected. It orders by layer, not by named
  preference, and discards why a provider was skipped.
- **Implicit `/data/jarvis.toml`:** rejected. A file only loads when `JARVIS_CONFIG` names it.

## Consequences
- Startup (not wired yet) calls `load_config()` → `detect()` → `resolve()`; the report feeds
  the LLM's self-description (#74).
- Store domains: `local` is available exactly when the store serves that domain locally, so
  local-first preference always agrees with `JARVIS_<DOMAIN>_PROVIDER`.

## Revisit when
Capabilities come from MCP at runtime (#68), or probes need hardware libraries.
