# Hive Architecture Design

_Last updated: 2026-03-24_

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

| Command | What it does |
|---|---|
| `/reset` | Clears the agent session for the current Telegram chat ID. The next message starts a fresh conversation with no prior context. Also clears any active session overrides. |
| `/help` | Lists all available commands (built-in + user-defined) with their descriptions. |
| `/menu` | Opens an inline keyboard launcher for quick command access. |
| `/set` | Override session config for the current conversation. See §4b. |

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
    permission_mode="bypassPermissions",
    cwd="/path/to/worker-folder",
    mcp_servers={"commands": commands_mcp_server, "builtins": builtins_mcp_server},
    model="claude-haiku-4-5",
    max_turns=10,
)
```

- `memory/` is the agent's primary read/write state store
- `commands/` scripts are exposed as tools via an in-process MCP server
- Agent sessions persist across messages (session ID stored in `.sessions.json`, keyed by Telegram chat ID)
- After each agent turn, Hive stages and commits any modified files to git

### Self-configuration

When no custom `agent_system_prompt` is set in `hive.toml`, the agent is instructed that it may modify `hive.toml` and `commands/`. After any interactive turn where those files change, the runtime detects the difference (via mtime comparison on `hive.toml` and `commands/*.py`) and:

1. Sends a "Config updated. Restarting…" message to the user
2. Schedules a SIGTERM after a 1.5 s delay — supervisord restarts the process with the new config

**Session continuity across restarts:** session IDs are persisted in `.sessions.json`, so conversation context survives a restart.

**Scheduled tasks do not trigger restart.** Change detection is wired only into the interactive NL message handler. Scheduled `agent_prompt` tasks intentionally skip it to avoid unattended restarts mid-schedule; supervisord will pick up any config changes on the next interactive turn.

**Error handling:** if the agent turn or Telegram delivery fails, change detection is skipped entirely. A partial write to `hive.toml` during an errored turn will not trigger a restart.

> **Note:** if `send_long_message` itself throws (e.g. a Telegram network error after a successful agent turn), the snapshot is never taken and no restart fires — even if config files were changed. This is intentional: if we couldn't confirm delivery, the worker treats the turn as inconclusive.

---

## 4b. Session Overrides

Agents and users can temporarily override `model`, `max_turns`, or `thinking_budget_tokens` for the current Telegram chat session without modifying `hive.toml`.

### Via the agent (`set_session_config` MCP tool)

The agent has access to a built-in `set_session_config` tool (exposed via an in-process `builtins` MCP server, separate from `commands/`). The agent can call it when the user asks to change settings for the current conversation:

```
set_session_config(model="claude-opus-4-6")
set_session_config(max_turns=20)
set_session_config(thinking_budget_tokens=8000)
```

Changes take effect from the **next** message (the current client is closed and rebuilt with the new options).

### Via the `/set` command (user-facing)

Users can set overrides directly without going through the agent:

```
/set model claude-opus-4-6
/set max_turns 20
/set thinking_budget_tokens 8000
/set reset          ← clear all overrides
```

`/set model` validates that the value starts with `claude-` and rejects it immediately if not.

### Override lifecycle

- Overrides are **in-memory only** — not written to `hive.toml`.
- Sequential `/set` calls **accumulate** (setting `model` then `max_turns` keeps both).
- Overrides are cleared by `/reset` or any worker restart (including config-triggered restarts).
- `thinking_budget_tokens` is stored as an integer override and translated to the SDK's `thinking: {type: "enabled", budget_tokens: N}` shape when the client is rebuilt.

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
