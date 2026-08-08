# Changelog

All notable changes to Hive will be documented in this file, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
See `docs/reference/versioning.md` for when to add an entry.

## [Unreleased]

## [0.3.0] - 2026-08-08

### Changed

- **Breaking:** `hive upgrade` renamed to `hive repair`. Same behavior
  (re-applies supervisord/LaunchAgent/LaunchDaemon configuration) — only the
  command name changed.

### Added

- `hive update <path> --bump` — after reviewing the changelog drift, records
  the installed Hive version as the Worker's new `hive_version` baseline.
  This is the one case where `hive update` writes to a Worker's files;
  without `--bump` it remains read-only.
- `hive start`, `hive restart`, and `hive status` now surface `hive_version`
  drift automatically, pointing at `hive update <path>` for details — no
  need to remember to check manually.

## [0.2.0] - 2026-08-04

### Added

- Every Worker's agent now has a built-in `write_page` tool for saving or
  updating durable knowledge pages under `memory/notes/`, with
  `memory/index.md` kept in sync automatically. Available by default, no
  `hive.toml` configuration needed.
- `memory/log.md` — an auto-maintained, chronological record of commands
  run, scheduled `agent_prompt` completions, saved notes, and files changed
  during chat. Deterministic (not agent-written); grep-friendly format
  (`## [YYYY-MM-DD HH:MM] <type> | <detail>`).
- Worker `hive.toml` now records the Hive version it was scaffolded against
  (`hive_version` in `[worker]`), stamped automatically by `hive init`.
- `hive update <path>` — reports what's changed in Hive since a Worker was
  scaffolded. Read-only; never modifies the Worker.
- `hive version` — prints the installed Hive version.

## [0.1.0b1] - 2026-04-16

Initial pre-release.
