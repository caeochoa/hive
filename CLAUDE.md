# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Hive** is a local-first framework for spinning up purpose-built Telegram bots called **Workers**. The central philosophy is **one folder = one world**: a Worker folder contains all its config, scripts, memory, and logs; Hive provides the shared infrastructure that runs them.

Key docs:
- `docs/reference/SPEC.md` — evergreen scope document: vocabulary, design philosophy, and architectural rationale
- `docs/reference/architecture.md` — diagrams (two-layer model, message routing), supervisord setup, worker folder structure, self-config edge cases
- `docs/features.md` — capability reference for worker developers; what Hive can do
- `docs/commands/README.md` — command script format, execution contract, agent tool wiring
- `docs/agent/README.md` — agent config, sessions, self-config, session overrides, extended thinking
- `docs/scheduling/README.md` — cron scheduling, `run` and `agent_prompt` job types
- `docs/dashboard/README.md` — all Comb cell types with examples
- `docs/cli/README.md` — complete CLI reference
- `docs/config/README.md` — canonical `hive.toml` and `.env` field reference

## Development Commands

This project uses `uv` for package management (Python 3.12).

```bash
uv sync              # install dependencies
uv run hive          # run the CLI
uv add <package>     # add a dependency
```

The `hive` CLI entry point is defined in `pyproject.toml` → `hive:main` → `src/hive/__init__.py`.

## Architecture

### Two distinct layers

1. **Hive** — installed once globally. Contains the CLI, Worker runtime, Comb dashboard server, and supervisord integration. Has its own Python environment.
2. **Worker folder** — pure data: `hive.toml`, `.env`, `commands/`, `memory/`, `logs/`, `dashboard/`. Workers are inert without Hive.

### Worker runtime model

Each `hive run <path>` process runs a single async event loop:
- Routes slash commands to `commands/` scripts (run as subprocesses in the Worker's `.venv`)
- Routes natural language messages to the Claude Agent SDK
- Runs scheduled tasks (APScheduler, same process)
- Auto-commits any file writes to the Worker's git repo after each turn
- Emits structured logs to stdout: `%(asctime)s %(name)s %(levelname)s %(message)s`

supervisord's `autorestart=true` handles crash recovery for the whole process.

### Command system

Scripts in `commands/` are dual-purpose: Telegram bot commands and agent tools.

**Metadata format** — structured docstring at the top of each script:

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
```

**Execution contract:**
- Hive invokes scripts as: `.venv/bin/python commands/<script>.py [--arg value | --flag]`
- Scripts may have a shebang line (`#!`) — Hive skips it when parsing docstrings
- `bool` args are passed as flags (`--name` only, no value); other types as `--name value`
- Stdout → Telegram reply
- Non-zero exit → error, stderr surfaced to user
- `WORKER_DIR` env var set by Hive so scripts can access Worker folder files

At startup, Hive scans `commands/`, parses docstrings, and registers both Telegram command handlers and MCP tool definitions for the agent.

### Agent design

Powered by the **Claude Agent SDK** (`claude-agent-sdk`). Key design points:
- Scoped to the Worker folder via `cwd` parameter
- Built-in filesystem tools: `Read`, `Write`, `Bash`, `Glob`
- `commands/` scripts exposed as tools via in-process MCP server (`commands` key)
- Built-in `set_session_config` tool exposed via a second MCP server (`builtins` key)
- `memory/` is the agent's primary read/write state store
- Agent sessions persist per Telegram chat ID (stored in `memory/.sessions.json`)
- Per-chat session overrides (model, max_turns, thinking_budget_tokens) held in memory; reset on `/reset` or restart
- Worker self-configuration: agent can edit `hive.toml`/`commands/*.py`; runtime detects changes and schedules SIGTERM self-restart
- Hive auto-commits any modified files after each agent turn
- All SDK activity (tool calls, thinking, cost) logged with structured tags: `[tool_use]`, `[tool_result]`, `[tool_error]`, `[thinking]`, `[result]`

### Secrets management

Secrets live in `.env` per Worker (git-ignored). Hive loads `.env` at startup.

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...        # single user; comma-separate for multiple: 12345,67890
```

`hive.toml` contains no secrets and is safe to commit.

### Configuration (`hive.toml`)

Full field reference: `docs/config/README.md`

```toml
[worker]
name = "budget"

[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
# system_prompt = "..."          # optional; disables self-config instructions if set
# thinking_budget_tokens = 5000  # optional; enables extended thinking

[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"

[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"

[comb]
cells = [
  { type = "log",      title = "Activity",    source = "logs/out.log" },
  { type = "markdown", title = "Summary",     source = "memory/summary.md" },
  { type = "metric",   title = "Tasks today", source = "memory/stats.json", key = "tasks_today" },
  { type = "status",   title = "Health",      source = "memory/health.json", key = "status" },
]
```

### Process management

Workers run as OS processes managed by **supervisord**. `hive start`/`hive stop` are wrappers over `supervisorctl`. supervisord starts on login via a macOS LaunchAgent (`~/Library/LaunchAgents/com.hive.supervisord.plist`), installed once by `hive init`.

### Comb (web dashboard)

A single centralised Hive web server serves all Workers at `<host>:8080/workers/<name>`. Binds to `0.0.0.0` (LAN-accessible). Config-driven — no custom code per Worker.

Cell types: `log`, `file`, `markdown`, `metric`, `status`, `table`, `chart`. Full reference: `docs/dashboard/README.md`.

### Hive CLI

Full reference: `docs/cli/README.md`

| Command | What it does |
|---|---|
| `hive init <name>` | Scaffold folder, git init, .venv, hive.toml + .env templates, register with supervisord, install LaunchAgent on first use |
| `hive start <path>` | Write supervisord block + `supervisorctl reread && update && start` |
| `hive stop <path>` | `supervisorctl stop` |
| `hive restart <path>` | `supervisorctl restart` |
| `hive remove <path>` | Unregister and stop a Worker; `--delete` also deletes the folder |
| `hive status` | `supervisorctl status` for all Workers |
| `hive logs <path>` | Tail Worker logs (`-n <lines>`, `-f` to follow) |
| `hive run <path>` | Internal — Worker entrypoint called by supervisord |
| `hive comb start/stop/restart` | Manage the Comb dashboard server |

## Key Entry Points

| What you want to understand | File | Where to start |
|---|---|---|
| All CLI commands | `src/hive/cli/app.py` | Top-level Typer commands |
| Worker boot sequence | `src/hive/worker/runtime.py` | `WorkerRuntime.start()` |
| Message routing (command vs NL) | `src/hive/worker/runtime.py` | `_handle_nl_message()`, `_register_handlers()` |
| Command discovery & execution | `src/hive/worker/commands.py` | `CommandRegistry.discover()` |
| Agent SDK integration | `src/hive/worker/agent.py` | `ClaudeAgentRunner.run()` |
| Built-in commands (/reset, /help, /menu, /set) | `src/hive/worker/builtins.py` | `make_*_handler()` functions |
| Built-in MCP tools (set_session_config) | `src/hive/worker/builtin_tools.py` | `build_builtin_mcp_server()` |
| Session overrides & self-config restart | `src/hive/worker/agent.py` | `set_session_override()`, `_run_interactive()` |
| All Pydantic data models | `src/hive/shared/models.py` | Top of file |
| Worker utilities (typing, formatting) | `src/hive/worker/utils.py` | `docs/guides/worker-internals.md` |
