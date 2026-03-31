# Feature Guide

A capability reference for Worker developers. Covers what Hive can do and how to configure each feature. Scannable in under five minutes.

---

## Commands

Write Python scripts in the `commands/` folder. Hive auto-discovers them on startup and registers each one as both a Telegram slash command and an MCP tool available to the agent.

Each script requires a YAML docstring at the top defining its metadata:

```python
"""
name: summarise
description: Summarise recent activity from the log
args:
  - name: n
    type: int
    description: Number of items to show
    default: 10
"""

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=10)
args = parser.parse_args()
print(f"Showing {args.n} items...")
```

Supported arg types: `str`, `int`, `float`, `bool`. Boolean args are passed as flags (`--flag` with no value). Stdout becomes the Telegram reply. Non-zero exit surfaces stderr as an error message.

> See also: [Commands reference](commands/README.md)

---

## Agent

Each Worker has a Claude agent that handles all natural language messages. The default model is `claude-haiku-4-5`. Configure it in the `[agent]` section of `hive.toml`:

```toml
[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
system_prompt = "You are a personal assistant. Keep responses concise."
```

The agent has access to built-in filesystem tools (`Read`, `Write`, `Bash`, `Glob`) and all `commands/` scripts as MCP tools. Sessions persist per Telegram chat ID across restarts, stored in `memory/.sessions.json`.

> See also: [Agent reference](agent/README.md)

---

## Session Overrides

Change agent configuration for your chat at runtime without restarting the Worker. Overrides are in-memory and apply immediately.

```
/set model claude-opus-4-5
/set max_turns 20
/set thinking_budget_tokens 8000
```

The agent itself can also call the `set_session_config` tool during a conversation to adjust its own settings. All overrides are reset by `/reset` or a Worker restart. To make a change permanent, edit `hive.toml` directly.

---

## Extended Thinking

Enable deeper reasoning for complex or multi-step tasks. Extended thinking causes the model to reason through a problem before responding.

Set it permanently in `hive.toml`:

```toml
[agent]
model = "claude-sonnet-4-5"
thinking_budget_tokens = 8000
```

Or enable it for your current session without restarting:

```
/set thinking_budget_tokens 8000
```

Trade-off: higher response quality for complex tasks, at higher cost and slower response time. Set to `0` or omit to disable.

---

## Worker Self-Configuration

The agent can modify its own `hive.toml` and `commands/*.py` files during an interactive turn. After the turn completes, Hive detects changes to these files and schedules a graceful self-restart so the new configuration takes effect automatically.

Sessions and overrides persist across self-config restarts. Self-config restarts only fire on interactive turns — never during scheduled task execution. You can inspect what changed in the Worker's git log:

```bash
git -C ./my-worker log --oneline -5
```

---

## Scheduling

Define cron jobs in `[[schedule]]` blocks in `hive.toml`. There are two types.

**Run a script on a schedule** — executes a command script and logs its output:

```toml
[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"
```

**Run an agent prompt on a schedule** — routes a prompt through the agent and sends the response to Telegram for each allowed user:

```toml
[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"
```

Each entry requires `cron` and exactly one of `run` or `agent_prompt`. Cron syntax follows standard five-field format.

> See also: [Scheduling reference](scheduling/README.md)

---

## Built-in Commands

Every Worker gets these slash commands automatically — no configuration needed:

| Command | Description |
|---|---|
| `/help` | Lists all available commands with an inline keyboard |
| `/menu` | Compact inline keyboard launcher for quick access |
| `/reset` | Clears the session and all in-memory overrides for your chat |
| `/set` | Runtime config override (see Session Overrides above) |

---

## Dashboard (Comb)

A config-driven web dashboard served at `http://localhost:8080/workers/<name>`. Define cells in the `[comb]` section of `hive.toml`:

```toml
[comb]
theme = "terminal-dark"
cells = [
  { type = "log",    title = "Activity",     source = "logs/out.log" },
  { type = "metric", title = "Tasks Today",  source = "memory/stats.json", key = "tasks_today" },
  { type = "status", title = "Health",       source = "memory/health.json", key = "status" },
]
```

Available cell types:

| Type | Renders |
|---|---|
| `log` | Live-tailing log via SSE |
| `file` | Plain text file (auto-renders `.md` as HTML) |
| `markdown` | Markdown file rendered as HTML |
| `metric` | Single value from a JSON object by key |
| `status` | Like `metric` but with semantic coloring (ok/warn/error) |
| `table` | JSON array of objects as an HTML table |
| `chart` | Numeric JSON data as a chart |

> See also: [Dashboard reference](dashboard/README.md)

---

## Multi-User

Set `TELEGRAM_ALLOWED_USER_ID` in `.env` to a comma-separated list of Telegram user IDs to allow multiple users to interact with the same Worker. Each user gets their own independent agent session.

```
TELEGRAM_ALLOWED_USER_ID=111111111,222222222,333333333
```

Get your Telegram user ID by sending `/start` to [@userinfobot](https://t.me/userinfobot).

---

## Memory and Auto-Commit

The `memory/` directory is the agent's primary state store. The agent reads and writes files there across sessions using its built-in `Read`, `Write`, `Bash`, and `Glob` tools.

After every agent turn, Hive automatically commits any modified files in these paths to the Worker's git repo:

```
commands/
memory/
hive.toml
dashboard/
```

Commit messages follow the format `hive: auto-commit after <reason>`. This gives you a full history of agent activity and makes it easy to roll back unwanted changes.
