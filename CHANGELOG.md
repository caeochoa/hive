# Changelog

All notable changes to Hive will be documented in this file, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
See `docs/reference/versioning.md` for when to add an entry.

## [Unreleased]

### Added

- Worker `hive.toml` now records the Hive version it was scaffolded against
  (`hive_version` in `[worker]`), stamped automatically by `hive init`.
- `hive update <path>` — reports what's changed in Hive since a Worker was
  scaffolded. Read-only; never modifies the Worker.
- `hive version` — prints the installed Hive version.

## [0.1.0b1] - 2026-04-16

Initial pre-release.
