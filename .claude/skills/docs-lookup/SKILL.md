---
name: docs-lookup
description: Fetch current, version-accurate library/framework/API documentation via the context7 MCP server before answering or coding against a dependency. Use whenever a question or task touches a specific library, framework, tool, SDK, or API — especially for version-specific behavior, config, or anything that may have changed since the knowledge cutoff.
---

# docs-lookup

Stay current instead of relying on memory. The training cutoff is stale for
fast-moving tooling (this repo's stack — uv, ruff, Tauri, Node, release-please,
pre-commit, the Anthropic/Claude API, etc. — all move faster than that).

## When to use
- Any task or question about a specific library/framework/tool/SDK/API.
- Anything version-specific: config keys, flags, options, migration, deprecations.
- Before writing non-trivial code against a dependency.
- When unsure whether remembered API details are still accurate.

## How
1. Resolve the library id with the context7 tool (e.g. `resolve-library-id`),
   passing the library name.
2. Fetch docs with `get-library-docs` for that id; scope with a topic and pin the
   version when it matters.
3. Ground the answer/code in what you retrieved. Cite the source when it resolves a
   non-obvious point.

## If context7 can't answer
Fall back to a targeted web search (WebSearch/WebFetch) for the official docs or
changelog. If the answer is still unclear, say so plainly and ask — do not guess at
version-specific behavior. (See the Operating principles in CLAUDE.md.)

## Notes
- The `context7` MCP server is configured in `.mcp.json`. An optional
  `CONTEXT7_API_KEY` (env / `.env`) raises rate limits; it works without one.
