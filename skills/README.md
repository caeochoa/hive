# Claude Code skills

These are personal Claude Code skills for building Hive Workers: `create-worker`, `add-command`, `add-schedule`, `setup-dashboard`. They live here so they're version-controlled and stay in sync with the docs they describe.

They're installed as **personal skills** (not project skills under a repo's `.claude/skills/`) because they need to be usable from any directory — e.g. a fresh folder for a new Worker outside this repo — not just when Claude Code's cwd is inside `hive/`.

## How they're linked

Each skill directory under `~/.claude/skills/` is a symlink to its counterpart here. This is Claude Code's supported mechanism for this exact case — see [Extend Claude with skills](https://code.claude.com/docs/en/skills): "A `<skill-name>` entry in the enterprise, personal, or project locations can be a symlink to a directory elsewhere on disk. Claude Code follows the symlink and reads `SKILL.md` from the target directory."

Editing a `SKILL.md` here takes effect immediately — Claude Code watches skill directories and picks up changes without a restart.

`telegram-bot-builder` and `telegram-mini-app` (also in `~/.claude/skills/`) are intentionally excluded — they're general third-party Telegram skills, not Hive-specific, so there's nothing here for them to drift out of sync with.

## Setting up on a new machine / clone

```bash
for d in create-worker add-command add-schedule setup-dashboard; do
  ln -s "$(pwd)/skills/$d" ~/.claude/skills/"$d"
done
```

Run from the repo root.
