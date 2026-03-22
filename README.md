# Hive

**Local-first framework for purpose-built Telegram bots**

Hive lets you spin up Claude-powered Telegram bots ("Workers") that live entirely in a folder. Each Worker has its own config, commands, memory, and logs. Hive provides the shared runtime, process management, and a web dashboard — Workers are inert without it.

---

## What is Hive?

The core idea is **one folder = one world**. A Worker folder contains everything that defines a bot: a `hive.toml` config, command scripts, memory files, and logs. Hive runs those Workers as supervised OS processes, routes Telegram messages to a Claude agent or command scripts, and exposes a config-driven **Comb** dashboard for monitoring.

---

## Features

- **Claude Agent SDK integration** — natural language messages are handled by a Claude agent with filesystem tools and access to your command scripts
- **Dual-purpose command scripts** — files in `commands/` register as both Telegram slash commands and agent tools
- **Scheduled tasks** — APScheduler cron entries can run scripts or fire agent prompts on a schedule
- **Config-driven Comb dashboard** — monitor logs, files, and metrics for all Workers from a single web UI
- **Auto-commit** — any files written by the agent are committed to the Worker's git repo after each turn
- **supervisord process management** — crash recovery via `autorestart=true`; start/stop via `hive` CLI

---

## Prerequisites

- Python 3.12
- [`uv`](https://github.com/astral-sh/uv)
- [`supervisord`](http://supervisord.org/) (`brew install supervisor` on macOS)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An Anthropic API key

---

## Installation

```bash
git clone <repo>
cd hive
uv install tool .
```

The `hive` CLI is now available via `hive`.

---

## Quick Start

### 1. Scaffold a Worker folder

```bash
hive init my-bot
```

This creates `./my-bot/`, registers it with supervisord, and installs a macOS LaunchAgent on first use so supervisord starts at login.

### 2. Configure secrets

Edit `my-bot/.env`:

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id
```

The `.env` file is git-ignored and never committed.

### 3. Add commands (optional)

Drop Python scripts in `my-bot/commands/`. Each script needs a metadata docstring:

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
import os, sys

n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 10
log = open(os.environ["WORKER_DIR"] + "/logs/out.log").readlines()
print("".join(log[-n:]))
```

### 4. Configure `hive.toml`

Edit `my-bot/hive.toml` to tune the agent, add schedules, and configure dashboard cells:

```toml
[worker]
name = "my-bot"

[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10

[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"

[comb]
cells = [
  { type = "log",    title = "Activity",    source = "logs/out.log" },
  { type = "file",   title = "Notes",       source = "memory/notes.md" },
]
```

### 5. Start the Worker

```bash
hive start ./my-bot
```

### 6. Open the dashboard

The Comb dashboard is served automatically at `http://localhost:8080/workers/my-bot`.

---

## Project Layout

```
my-bot/
├── hive.toml           # Worker config (safe to commit)
├── .env                # Secrets (git-ignored)
├── requirements.txt    # Worker-specific Python dependencies
├── .gitignore
├── commands/           # Command scripts (Telegram commands + agent tools)
│   └── summarise.py
├── memory/             # Agent read/write state store
│   └── notes.md
├── logs/               # Runtime logs (git-ignored)
│   └── out.log
└── dashboard/          # Reserved for custom dashboard assets
```

---

## Configuration Reference

```toml
[worker]
name = "my-bot"                # Used as the supervisord process name and dashboard URL slug

[agent]
model = "claude-haiku-4-5"     # Claude model for natural language messages
memory_dir = "memory/"         # Directory the agent treats as primary state store
max_turns = 10                 # Maximum agentic turns per message

# Scheduled tasks — run on a cron schedule
[[schedule]]
cron = "0 8 * * *"             # Standard cron expression
run = "commands/morning_brief.py"   # Run a command script

[[schedule]]
cron = "0 9 * * 1"             # Every Monday at 9am
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"

# Comb dashboard cells
[comb]
cells = [
  # Tail a log file, auto-refreshing
  { type = "log",    title = "Activity",    source = "logs/out.log" },
  # Render a Markdown or plain text file
  { type = "file",   title = "Summary",     source = "memory/summary.md" },
  # Extract a single value from a JSON file
  { type = "metric", title = "Tasks today", source = "memory/stats.json", key = "tasks_today" },
]
```

---

## Writing Commands

Scripts in `commands/` are executed by Hive as subprocesses using the Worker's `.venv`. They double as agent tools.

**Metadata docstring** (required, at the top of the file):

```python
"""
name: remind
description: Set a reminder message
args:
  - name: message
    type: str
    description: The reminder text
  - name: urgent
    type: bool
    description: Mark as urgent
    default: false
"""
```

**Execution contract:**

| Detail | Behaviour |
|--------|-----------|
| Invocation | `.venv/bin/python commands/<script>.py [--arg value \| --flag]` |
| `bool` args | Passed as flags (`--urgent`, no value) |
| Other args | Passed as `--name value` |
| `WORKER_DIR` | Env var pointing to the Worker folder root |
| stdout | Sent back to Telegram as a reply |
| Non-zero exit | Error surfaced to the user; stderr shown |

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `hive init <name>` | Scaffold a Worker folder, register with supervisord, install LaunchAgent on first use |
| `hive start <path>` | Start a Worker process |
| `hive stop <path>` | Stop a Worker process |
| `hive restart <path>` | Restart a Worker process |
| `hive remove <path>` | Unregister and stop a Worker (add `--delete` to also delete the folder) |
| `hive status` | Show status of all Workers |
| `hive logs <path>` | Tail Worker logs (`-n <lines>`, `-f` to follow) |

---

## Architecture Overview

Hive has two distinct layers:

**Hive** is installed once. It provides the CLI, Worker runtime, Comb dashboard server, and supervisord integration.

**Worker folders** are pure data. They contain config, scripts, memory, and logs, but are inert without Hive running them.

Each `hive run <path>` process runs a single async event loop that:
1. Routes Telegram slash commands to `commands/` scripts (run as subprocesses in the Worker's `.venv`)
2. Routes natural language messages to a Claude agent (Claude Agent SDK)
3. Executes scheduled tasks (APScheduler)
4. Auto-commits any file writes to the Worker's git repo

supervisord's `autorestart=true` handles crash recovery. On macOS, a LaunchAgent starts supervisord at login.

For full design details see [`docs/plans/SPEC.md`](docs/plans/SPEC.md).

---

## Development

```bash
uv sync              # install dependencies
uv run hive          # run the CLI
uv run pytest        # run tests
uv add <package>     # add a dependency
```
