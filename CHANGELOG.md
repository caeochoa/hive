# Changelog

All notable changes to Hive will be documented in this file, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
See `docs/reference/versioning.md` for when to add an entry.

## [Unreleased]

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
