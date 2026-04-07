# Configuration Reference

Each Worker is configured by two files in its folder: `.env` (secrets, git-ignored) and `hive.toml` (everything else).

---

## `.env`

Required. Never committed to git.

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USER_ID` | Yes | Your Telegram user ID. Comma-separated for multiple users: `12345,67890` |

```dotenv
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_ALLOWED_USER_ID=123456789
```

To find your Telegram user ID, message [@userinfobot](https://t.me/userinfobot).

---

## `hive.toml`

The main configuration file. Safe to commit. Contains no secrets.

### `[worker]`

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Worker identifier. Used in supervisord process names and Comb dashboard URLs (`/workers/<name>`) |

```toml
[worker]
name = "budget"
```

---

### `[agent]`

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | string | `"claude-haiku-4-5"` | Claude model ID |
| `memory_dir` | string | `"memory/"` | Agent memory directory, relative to worker dir |
| `max_turns` | int | `10` | Max agent turns per incoming message |
| `system_prompt` | string | _(none)_ | Custom system prompt. If set, self-configuration instructions are not added |
| `thinking_budget_tokens` | int | _(none)_ | Token budget for extended thinking. Omit to disable |

```toml
[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
# system_prompt = "You are a budget tracker. Be concise."
# thinking_budget_tokens = 5000
```

Note: setting `system_prompt` disables the default self-config instructions. The agent will not know it can edit `hive.toml` or `commands/` unless you include that guidance yourself.

---

### `[[schedule]]`

Repeatable. Each entry defines one scheduled task.

| Field | Type | Required | Description |
|---|---|---|---|
| `cron` | string | Yes | 5-field cron expression (`minute hour day month weekday`) |
| `run` | string | Mutually exclusive with `agent_prompt` | Path to a command script to execute |
| `agent_prompt` | string | Mutually exclusive with `run` | Prompt to run through the agent on a schedule |
| `skip_if_five_hour_above` | float | No | Skip this job if Claude 5-hour usage is at or above this percentage (0–100). Missing or stale data is treated as allow. |
| `skip_if_seven_day_above` | float | No | Skip this job if Claude 7-day usage is at or above this percentage (0–100). Missing or stale data is treated as allow. |
| `notify_on_skip` | bool | No (default `true`) | Send a Telegram message when the job is skipped due to usage thresholds. Set to `false` for silent skipping. |

Exactly one of `run` or `agent_prompt` must be set.

```toml
# Run a script every day at 8am
[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"

# Run an agent prompt every Monday at 9am
[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"

# Skip the job if usage is high; notify via Telegram when skipped
[[schedule]]
cron = "0 12 * * *"
agent_prompt = "Run the midday analysis"
skip_if_five_hour_above = 80.0
skip_if_seven_day_above = 90.0
notify_on_skip = true   # default; set false for silent skipping
```

---

### `[comb]`

Controls the Comb web dashboard at `<host>:8080/workers/<name>`.

| Field | Type | Default | Description |
|---|---|---|---|
| `theme` | string | `"terminal-dark"` | Dashboard theme |
| `cells` | array | `[]` | List of dashboard cell objects (see below) |

#### Cell fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Cell type (see table below) |
| `title` | string | Yes | Display title shown in the dashboard |
| `source` | string | Yes | Path to source file, relative to worker dir. For `file`/`markdown` types, can be a directory — uses the most recently modified file |
| `key` | string | Required for `metric`, `status` | JSON key to extract from the source file |

#### Cell types

| Type | Renders |
|---|---|
| `log` | Tail of a log file, auto-refreshing |
| `file` | Plain text file |
| `markdown` | Markdown file rendered as HTML |
| `metric` | Single numeric or string value from a JSON file (requires `key`) |
| `status` | Status value from a JSON file (requires `key`) |
| `table` | Tabular data |
| `chart` | Chart visualization |

```toml
[comb]
theme = "terminal-dark"

[[comb.cells]]
type = "log"
title = "Activity"
source = "logs/out.log"

[[comb.cells]]
type = "file"
title = "Notes"
source = "memory/notes.md"

[[comb.cells]]
type = "metric"
title = "Tasks today"
source = "memory/stats.json"
key = "tasks_today"
```

The same configuration can be written using inline table array syntax:

```toml
[comb]
theme = "terminal-dark"
cells = [
  { type = "log",    title = "Activity",    source = "logs/out.log" },
  { type = "file",   title = "Notes",       source = "memory/notes.md" },
  { type = "metric", title = "Tasks today", source = "memory/stats.json", key = "tasks_today" },
]
```


---

## Complete annotated example

```toml
# ── Worker identity ────────────────────────────────────────────────────────────
[worker]
name = "budget"

# ── Agent settings ─────────────────────────────────────────────────────────────
[agent]
# Claude model to use for natural language messages.
model = "claude-haiku-4-5"

# Directory for agent memory files and session state (.sessions.json).
memory_dir = "memory/"

# Maximum agent turns per incoming message. Raise if tasks require deeper
# multi-step reasoning; lower to reduce latency and cost.
max_turns = 10

# Optional: custom system prompt. Removes self-config instructions.
# system_prompt = "You are a personal budget assistant. Be concise."

# Optional: enable extended thinking with a token budget.
# Higher quality on complex tasks; increases cost and latency.
# thinking_budget_tokens = 5000

# ── Scheduled tasks ────────────────────────────────────────────────────────────

# Run a script on a cron schedule.
[[schedule]]
cron = "0 8 * * *"          # daily at 8am
run = "commands/morning_brief.py"

# Run an agent prompt on a cron schedule.
[[schedule]]
cron = "0 9 * * 1"          # every Monday at 9am
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"

# Skip if Claude usage is high; notify via Telegram when skipped.
[[schedule]]
cron = "0 12 * * *"         # daily at noon
agent_prompt = "Run the midday analysis"
skip_if_five_hour_above = 80.0
skip_if_seven_day_above = 90.0
# notify_on_skip = true     # default; set false for silent skipping

# ── Comb dashboard ─────────────────────────────────────────────────────────────
[comb]
theme = "terminal-dark"

# Tail of the worker log file, auto-refreshing.
[[comb.cells]]
type = "log"
title = "Activity"
source = "logs/out.log"

# Render a markdown file.
[[comb.cells]]
type = "file"
title = "Weekly Summary"
source = "memory/weekly.md"

# Extract a single value from a JSON file.
[[comb.cells]]
type = "metric"
title = "Tasks today"
source = "memory/stats.json"
key = "tasks_today"
```
