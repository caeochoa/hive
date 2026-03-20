# Hive Architecture Design

_Last updated: 2026-03-09_

---

## 1. Two-Layer Model

Hive has two immutable layers:

```
┌─────────────────────────────────────────────────────┐
│  HIVE  (installed once, one Python process per Worker)│
│                                                     │
│  CLI │ Worker Runtime │ Comb Server │ supervisord   │
└─────────────────────────────────────────────────────┘
         │ points at │
┌────────▼────────────┐  ┌─────────────────────────┐
│  Worker Folder A    │  │  Worker Folder B         │
│  hive.toml          │  │  hive.toml               │
│  .env               │  │  .env                    │
│  commands/          │  │  commands/               │
│  memory/            │  │  memory/                 │
│  logs/              │  │  logs/                   │
└─────────────────────┘  └──────────────────────────┘
```

- **Hive** — installed once globally. Contains CLI, Worker runtime, Comb server, supervisord integration. Has its own Python environment.
- **Worker folder** — pure data: config, scripts, memory, logs. Inert without Hive.

---

## 2. Worker Runtime

Each `hive run <path>` process runs a single async event loop with four subsystems:

```
                    Telegram message arrives
                            │
                    ┌───────▼────────┐
                    │  Auth guard    │  (ALLOWED_USER_ID from .env)
                    └───────┬────────┘
                            │
              ┌─────────────▼──────────────┐
              │  Is it a slash command?    │
              └──────┬──────────┬──────────┘
                    yes         no
                     │          │
          ┌──────────▼──┐  ┌────▼──────────────┐
          │  Command    │  │   NL Handler      │
          │  dispatcher │  │   (Agent runner)  │
          └──────┬──────┘  └────────┬──────────┘
                 │                  │
          ┌──────▼──────┐  ┌────────▼──────────┐
          │  Run script │  │  Claude Agent SDK │
          │  as subprocess  │  (session-aware)  │
          └──────┬──────┘  └────────┬──────────┘
                 │                  │
                 └────────┬─────────┘
                          │
                  ┌───────▼────────┐
                  │  Hive commits  │  (git, after any writes)
                  └───────┬────────┘
                          │
                  ┌───────▼────────┐
                  │  Reply to user │
                  └────────────────┘
```

**Scheduler** runs as a parallel async task in the same process (APScheduler), firing scripts or agent prompts on cron schedule. Scheduled `agent_prompt` responses are sent to the user's Telegram chat (using `TELEGRAM_ALLOWED_USER_ID`). supervisord's `autorestart=true` handles crash recovery for both the bot and scheduler together.

---

## 3. Command System

Scripts in `commands/` are dual-purpose: Telegram bot commands and agent tools.

### Metadata format

Structured docstring at the top of each script:

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
import sys
# ... script body
```

### Execution contract

Hive invokes scripts as subprocesses inside the Worker's `.venv`:

```
.venv/bin/python commands/summarise.py --n 10
```

- Args passed as CLI flags (`--name value`)
- Stdout captured and sent as Telegram reply
- Non-zero exit code = error, stderr surfaced to user
- `WORKER_DIR` env var set by Hive so scripts can read/write Worker folder files
- File writes are picked up by Hive's auto-commit after the script exits

### At startup

Hive scans `commands/`, parses docstrings, and builds two registrations:
1. **Telegram command handlers** — one per script, registered with python-telegram-bot
2. **MCP tool definitions** — for the agent; MCP server wraps the same subprocess calls

A script works identically whether triggered by `/summarise 10` or by the agent calling the `summarise` tool.

---

## 3b. Built-in Hive Commands

Some commands are built into Hive itself — present on every Worker regardless of what's in `commands/`, not authored by the Worker developer, and not exposed as agent tools. They are meta/control commands that operate on the Worker runtime rather than on Worker data.

**Initial set:**

| Command | What it does |
|---|---|
| `/reset` | Clears the agent session for the current Telegram chat ID. The next message starts a fresh conversation with no prior context. |
| `/help` | Lists all available commands (built-in + user-defined) with their descriptions. |

Built-in handlers are registered by `WorkerRuntime` directly, before user-defined commands. They take precedence: if a user creates `commands/reset.py`, Hive logs a warning and the built-in wins.

Built-in commands are **not** exposed as agent tools — they control the runtime, not the Worker's domain logic.

---

## 4. Agent

The agent is powered by the Claude Agent SDK, scoped to the Worker folder:

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt="You are a worker agent. Your world is this folder.",
    allowed_tools=["Read", "Write", "Bash", "Glob"],
    permission_mode="acceptEdits",
    cwd="/path/to/worker-folder",
    mcp_servers={"commands": commands_mcp_server},
    model="claude-haiku-4-5",
    max_turns=10,
)
```

- `memory/` is the agent's primary read/write state store
- `commands/` scripts are exposed as tools via an in-process MCP server
- Agent sessions persist across messages (session ID stored in memory, keyed by Telegram chat ID)
- After each agent turn, Hive stages and commits any modified files to git

---

## 5. Configuration

### `.env` (git-ignored, secrets only)

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...
```

### `hive.toml` (committed, no secrets)

```toml
[worker]
name = "budget"

[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10

[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"

[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"

[comb]
cells = [
  { type = "log",    title = "Activity",    source = "logs/worker.log" },
  { type = "file",   title = "Summary",     source = "memory/summary.md" },
  { type = "metric", title = "Tasks today", source = "memory/stats.json", key = "tasks_today" },
]
```

The Telegram token lives in `.env` so `hive.toml` can be safely committed.

### Comb cell types (MVP)

| Type | Renders |
|---|---|
| `log` | Tail of a log file, auto-refreshing |
| `file` | Markdown or plain text file |
| `metric` | Single value extracted from a JSON file by key |

---

## 6. Process Management

### supervisord

Each Worker is registered as a program block:

```ini
[program:worker-budget]
command=hive run /path/to/budget
directory=/path/to/budget
autostart=true
autorestart=true
stdout_logfile=/path/to/budget/logs/out.log
stderr_logfile=/path/to/budget/logs/err.log
```

### macOS LaunchAgent

supervisord itself starts on user login via `~/Library/LaunchAgents/com.hive.supervisord.plist`. Installed once during `hive init` on first use, alongside the Comb supervisord block.

### Hive CLI

| Command | What it does |
|---|---|
| `hive init <name>` | Scaffold folder, git init, .venv, hive.toml + .env templates, register with supervisord, install LaunchAgent + Comb block on first use |
| `hive start <path>` | Write supervisord block + `supervisorctl reread && update && start` |
| `hive stop <path>` | `supervisorctl stop` |
| `hive restart <path>` | `supervisorctl restart` |
| `hive remove <path>` | Stop Worker, remove supervisord block, unregister from HiveRegistry. Use `--delete` to also delete the folder (prompts for confirmation). |
| `hive status` | `supervisorctl status` for all Workers |
| `hive logs <path>` | Tail Worker logs |
| `hive run <path>` | Internal — Worker entrypoint called by supervisord |
| `hive comb` | Internal — Comb server entrypoint called by supervisord |

---

## 7. Comb (Web Dashboard)

A single Hive-managed web server serves all Workers' dashboards:

- URL pattern: `localhost:8080/workers/<name>`
- Config-driven: Workers declare cells in `hive.toml`, no custom code required
- Cell types: `log`, `file`, `metric` (MVP)
- Runs as its own supervisord program (`hive-comb`), started once on first `hive init`
- Reads `HiveRegistry` at startup to discover all registered Workers
- Entrypoint: `hive comb` (internal CLI command, not for direct user use)

---

## 8. Worker Folder Structure

```
my-worker/
├── .git/                  # All changes tracked
├── .gitignore             # Ignores .env, .venv/, logs/, *.pyc, __pycache__/, *.tmp, .DS_Store
├── .venv/                 # Scripts-only venv (not for Hive itself)
├── .env                   # Secrets (git-ignored)
├── hive.toml              # Worker config
├── commands/              # Scripts = bot commands = agent tools
│   ├── summarise.py
│   └── fetch_news.py
├── memory/                # Agent state, notes, working memory
├── logs/                  # Worker output (written by supervisord)
└── dashboard/             # Optional static assets for the Comb
```
