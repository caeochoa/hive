# Versioning & Changelog Conventions

_Last updated: 2026-08-01_

---

## For Hive contributors

- Hive's own version lives in `pyproject.toml` under `[project] version`, and
  is read at runtime as `hive.__version__` (backed by
  `importlib.metadata.version("hive")`).
- Add a `CHANGELOG.md` entry under `## [Unreleased]` for any change that:
  - adds, removes, or renames a `hive.toml` or `.env` field a Worker
    developer would notice,
  - adds or removes a CLI command, or changes an existing command's
    behavior or output in a user-visible way,
  - changes agent/runtime behavior a Worker developer configured around,
  - fixes a bug a Worker developer likely hit.

  Purely internal refactors, test-only changes, and docs-only changes don't
  need an entry.
- What counts as "breaking" for a Worker developer: anything that requires
  them to edit their `hive.toml`, `.env`, or `commands/` to keep working, or
  that silently changes behavior they may be relying on. Flag these clearly
  (e.g. a `**Breaking:**`-prefixed bullet) so `hive update`'s excerpt makes
  the stakes obvious.
- Bumping `pyproject.toml`'s version and cutting a release/tag is a manual,
  human decision — not automated by this repo. At release time, move the
  `[Unreleased]` section's contents under a new `## [x.y.z] - YYYY-MM-DD`
  heading and tag `vX.Y.Z`.

## For Worker developers

- Every Worker's `hive.toml` records the Hive version it was scaffolded
  against, in `[worker] hive_version`. Hive never rewrites this after
  `hive init` — it's a one-time stamp, not something kept in sync
  automatically.
- Run `hive update <path>` after upgrading Hive to see what's changed since
  your Worker was created. This only reports — it never rewrites your
  `hive.toml` or any other file. If a change affects you, apply it by hand.
- Workers created before this feature existed have no `hive_version` field;
  `hive update` treats these as an unknown baseline and shows full history
  up to the installed version.
- `hive update` is unrelated to `hive upgrade`: `upgrade` re-applies process
  management config (supervisord, LaunchAgent/LaunchDaemon) and never looks
  at a Worker's `hive.toml`; `update` only reports Hive version drift for a
  single Worker and never touches process config.
