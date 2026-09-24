# 0005. Local SQLite state store with local-first providers
Status: Accepted · Date: 2026-09-24

## Context
Jarvis must work standalone (work Pi, laptop) yet use Faelab's data at home (#75). Its own
state must be cheap to snapshot and restore around a promote/rollback (#67).

## Decision
- **One SQLite file** via the stdlib `sqlite3`: WAL mode, one connection per store behind a
  lock, calls run in `asyncio.to_thread` so the event loop never blocks.
- **Forward-only migrations** tracked in `PRAGMA user_version`. Each migration records
  `min_reader`, the oldest schema version that can still read the file (kept in
  `schema_meta`). Additive migrations (new tables, or nullable/defaulted columns) keep it,
  so the previous release still opens the file after a rollback. A breaking one raises it.
  A build opens a newer file only if its schema version is at least `min_reader`, and never
  downgrades it. Otherwise it refuses.
- **One async `Protocol` per domain** (notes, todo, calendar, key-value, memory,
  notifications). Notes, todo and calendar can be switched to a Faelab provider per domain
  by env. The rest is Jarvis-owned and always local.
- **Snapshot/restore** use SQLite's online backup API, which gives one self-contained file.
  Restore checks integrity, reader compatibility and the expected tables, and migrates a
  scratch copy first. The live database changes only if all of that succeeds.

## Alternatives
- **aiosqlite or an ORM (SQLAlchemy/SQLModel):** rejected. They add dependencies for a few
  small tables, and `to_thread` plus a lock does the same job.
- **Postgres or another server:** rejected. It is a second service on the Pi, and snapshots
  would need dumps.
- **JSON files:** rejected. They have no transactions, no range queries, and concurrent
  writes are unsafe.

## Consequences
- The agent image provides a `jarvis`-owned `/data`; compose still needs a named volume
  there for the DB file to persist.
- Faelab providers plug in through `FaelabProviders` once capabilities (#72) exist.

## Revisit when
Several processes need to write the store, or its size makes snapshots slow.
