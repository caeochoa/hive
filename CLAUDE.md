# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Hive** is a local-first framework for spinning up purpose-built Telegram bots called **Workers**. The central philosophy is **one folder = one world**: a Worker folder contains all its config, scripts, memory, and logs; Hive provides the shared infrastructure that runs them.

Key docs:
- `docs/plans/SPEC.md` — evergreen scope document: what Hive is, vocabulary, components, and design decisions
- `docs/plans/2026-03-09-hive-architecture-design.md` — concrete implementation detail: data flows, config schemas, CLI contract, supervisord setup

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
- Hive invokes scripts as: `.venv/bin/python commands/<script>.py --arg value`
- Stdout → Telegram reply
- Non-zero exit → error, stderr surfaced to user
- `WORKER_DIR` env var set by Hive so scripts can access Worker folder files

At startup, Hive scans `commands/`, parses docstrings, and registers both Telegram command handlers and MCP tool definitions for the agent.

### Agent design

Powered by the **Claude Agent SDK** (`claude-agent-sdk`). Key design points:
- Scoped to the Worker folder via `cwd` parameter
- Built-in filesystem tools: `Read`, `Write`, `Bash`, `Glob`
- `commands/` scripts exposed as tools via in-process MCP server
- `memory/` is the agent's primary read/write state store
- Agent sessions persist per Telegram chat ID (session ID stored in `memory/`)
- Hive auto-commits any modified files after each agent turn

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

### Secrets management

Secrets live in `.env` per Worker (git-ignored). Hive loads `.env` at startup.

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...
```

`hive.toml` contains no secrets and is safe to commit.

### Configuration (`hive.toml`)

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

### Process management

Workers run as OS processes managed by **supervisord**. `hive start`/`hive stop` are wrappers over `supervisorctl`. supervisord starts on login via a macOS LaunchAgent (`~/Library/LaunchAgents/com.hive.supervisord.plist`), installed once by `hive init`.

### Comb (web dashboard)

A single centralised Hive web server serves all Workers at `localhost:8080/workers/<name>`. Config-driven — no custom code per Worker.

MVP cell types:

| Type | Renders |
|---|---|
| `log` | Tail of a log file, auto-refreshing |
| `file` | Markdown or plain text file |
| `metric` | Single value extracted from a JSON file by key |

### Hive CLI

| Command | What it does |
|---|---|
| `hive init <name>` | Scaffold folder, git init, .venv, hive.toml + .env templates, register with supervisord, install LaunchAgent on first use |
| `hive start <path>` | Write supervisord block + `supervisorctl reread && update && start` |
| `hive stop <path>` | `supervisorctl stop` |
| `hive restart <path>` | `supervisorctl restart` |
| `hive status` | `supervisorctl status` for all Workers |
| `hive logs <path>` | Tail Worker logs |
| `hive run <path>` | Internal — Worker entrypoint called by supervisord |
