# Versioning & Changelog Conventions

_Last updated: 2026-08-08_

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
- Hive has no separate publish step — it's installed as a single editable
  checkout, so "merged to `main`" and "released" are the same thing. Any PR
  that adds a `CHANGELOG.md` entry under `[Unreleased]` must, **in that same
  PR**, also bump `pyproject.toml`'s `[project] version` and move the
  `[Unreleased]` section's contents (that entry and anything else already
  sitting there) under a new `## [x.y.z] - YYYY-MM-DD` heading, then tag
  `vX.Y.Z`. `[Unreleased]` should be empty on `main` between PRs — it's a
  within-PR staging area, not a backlog. This keeps `hive_version`
  comparisons and `hive update`'s output accurate as of the latest merge.
- Any PR that adds or changes a user-visible feature must update
  `docs/features.md` in that same PR, alongside the `CHANGELOG.md` entry.
  `docs/features.md` is the capability reference Worker developers scan to
  learn what Hive can do — it should always describe what's actually
  shipped on `main`, not lag behind it.

## For Worker developers

- Every Worker's `hive.toml` records the Hive version it was scaffolded
  against, in `[worker] hive_version`. Hive never rewrites this on its own —
  it only changes when you run `hive update <path> --bump` (see below).
- Run `hive update <path>` any time to see what's changed since your Worker
  was created. By default this only reports — it never rewrites your
  `hive.toml` or any other file. If a change affects you, apply it by hand.
- `hive update <path> --bump` is the one way `hive update` writes to a
  Worker: after printing the drift report, it rewrites `hive_version` in
  `hive.toml` to the installed Hive version, leaving the rest of the file
  untouched. Use it once you've reviewed the changes and confirmed nothing
  affects you — it's a manual opt-in, never automatic.
- You don't have to run `hive update` proactively to notice drift: `hive
  start`/`hive restart` print a short note if the Worker's `hive_version` is
  behind, and `hive status` flags every drifted Worker in its output. Both
  point you at `hive update <path>` for the full changelog excerpt.
- Workers created before this feature existed have no `hive_version` field;
  `hive update` treats these as an unknown baseline and shows full history
  up to the installed version.
- `hive update` is unrelated to `hive repair`: `repair` re-applies process
  management config (supervisord, LaunchAgent/LaunchDaemon) across every
  registered Worker and never looks at a Worker's `hive.toml`; `update`
  only reports (and, with `--bump`, records) Hive version drift for a
  single Worker, and never touches process config. `repair` is something
  you run rarely — after a Hive upgrade or a reboot leaves Workers not
  starting; `update` is meant to be a routine, low-friction check.
- `hive update` may make a single outbound HTTPS request (to fetch
  `CHANGELOG.md` from GitHub) when running from a non-source install that
  doesn't have the file on disk. It never sends any Worker data — only a
  read-only fetch of the public changelog file.
