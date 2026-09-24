# 0005. Local SQLite state store with local-first providers
Status: Accepted · Date: 2026-09-24

## Context
Jarvis must work standalone (work Pi, laptop) yet use Faelab's data at home (#75). Its own
state must be cheap to snapshot and restore around a promote/rollback (#67).

## Decision
- **One SQLite file** via the stdlib `sqlite3`: WAL mode, one connection per store behind a
  lock, calls run in `asyncio.to_thread` so the event loop never blocks.
- **Forward-only migrations** tracked in `PRAGMA user_version`. A newer schema is refused.
  Migrations only add, so the previous release can still read the file.
- **One async `Protocol` per domain** (notes, todo, calendar, key-value, memory,
  notifications). Notes, todo and calendar can be switched to a Faelab provider per domain
  by env. The rest is Jarvis-owned and always local.
- **Snapshot/restore** use SQLite's online backup API, which gives one self-contained file.

## Alternatives
- **aiosqlite or an ORM (SQLAlchemy/SQLModel):** rejected. They add dependencies for a few
  small tables, and `to_thread` plus a lock does the same job.
- **Postgres or another server:** rejected. It is a second service on the Pi, and snapshots
  would need dumps.
- **JSON files:** rejected. They have no transactions, no range queries, and concurrent
  writes are unsafe.

## Consequences
- The agent image needs a persistent volume for the DB file.
- Faelab providers plug in through `FaelabProviders` once capabilities (#72) exist.

## Revisit when
Several processes need to write the store, or its size makes snapshots slow.
