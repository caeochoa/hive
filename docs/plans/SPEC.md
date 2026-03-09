# 🐝 Hive

**Project Specification — v0.2**
_Last updated: March 2026_

---

## 1. Overview

Hive is a local-first personal framework for spinning up purpose-built Telegram bots, called Workers. Each Worker is a self-contained process with its own folder, agent, scripts, and optional web dashboard. Hive is the framework that brings Workers to life — Workers are inert folders without it.

The central design philosophy is: **one folder = one world**. A Worker folder contains everything specific to that bot, while Hive provides the shared infrastructure that runs them all.

---

## 2. Vocabulary

| Term | Definition |
|---|---|
| **Hive** | The framework. Installed once, lives outside worker folders. Manages process lifecycle, runs event loops, hosts dashboards. |
| **Worker** | A long-running bot process. The full system: event loop, Telegram interface, agent, scheduler, and dashboard. Not just the agent. |
| **Agent** | The LLM reasoning component inside a Worker. Only invoked when complex reasoning is needed — the prefrontal cortex, not the whole brain. |
| **Commands** | Scripts in the `commands/` folder. Serve dual purpose: callable as bot commands by users, and as tools by the agent. |
| **Comb** | The per-Worker web dashboard. Displays output panels without requiring custom code per worker. |
| **Cell** | An individual panel within the Comb. Configured declaratively in `hive.toml`. |

---

## 3. Architecture

### 3.1 Hive vs Worker

There are two distinct layers:

- **Hive** — installed globally on the host machine. Contains the event loop, Telegram integration, agent runner, scheduler, and Comb server. Has its own Python environment.
- **Worker folder** — contains only data: config, scripts, memory, logs. The `.venv` inside the worker folder is exclusively for scripts/commands, not for running the worker itself.

A Worker is brought to life by pointing Hive at its folder:

```bash
hive start ./my-worker
```

### 3.2 Worker Folder Structure

```
my-worker/
├── .git/                  # All changes tracked
├── .venv/                 # Scripts-only venv
├── .env                   # Secrets (git-ignored)
├── hive.toml              # Worker config
├── commands/              # Scripts = bot commands = agent tools
│   ├── summarise.py
│   └── fetch_news.py
├── memory/                # Agent state, notes, working memory
├── logs/                  # Worker output
└── dashboard/             # Optional static assets for the Comb
```

### 3.3 Worker as Brain

The Worker is not the agent. The Worker is an event loop that runs continuously, routing messages, firing scripts, and managing state. The Agent is one subsystem of the Worker — invoked only when a task requires LLM reasoning. Routine commands run as plain scripts without touching the LLM.

---

## 4. Worker Components

### 4.1 Telegram Interface

- Every Worker has a Telegram bot as its primary interface.
- Users interact via bot commands (e.g. `/summarise`, `/fetch`).
- Commands map directly to scripts in the `commands/` folder.
- Commands are auto-discovered from `commands/` at startup and registered with Telegram.
- Auth is controlled via `TELEGRAM_ALLOWED_USER_ID` in `.env` — only that user ID can interact with the bot.

### 4.2 Agent

- An LLM agent runs inside each Worker, invoked on demand for natural language messages.
- The agent has access to the Worker's folder as its memory and state.
- The agent's tools are auto-discovered from the `commands/` folder. Each script exposes a metadata block (description, args schema) that the Worker registers at startup.
- `memory/` is the agent's primary read/write state store — free-form files, no structured store required.
- Hive auto-commits any modified files after each agent turn, so the git repo acts as an audit trail for all agent writes.
- Agent sessions persist per Telegram chat ID.

**Decision: the agent is powered by the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)** (`pip install claude-agent-sdk`). It runs on the existing Claude Code installation and inherits its authentication — no API key or separate billing required for personal local use. The SDK provides built-in filesystem tools (`Read`, `Write`, `Bash`, `Glob`) and supports a `cwd` parameter to scope the agent to the Worker's folder, which maps directly onto the "one folder = one world" design. Custom tools are registered as in-process MCP servers, which is how `commands/` scripts are exposed to the agent.

### 4.3 Commands

- Scripts in `commands/` serve as both bot commands (user-facing) and agent tools (LLM-facing).
- Each script exposes a metadata block at the top — a structured YAML docstring with name, description, and args — used for both Telegram command registration and agent tool schema generation.
- Scripts run inside the Worker's `.venv`, allowing per-worker dependencies.
- Hive invokes scripts with args as CLI flags; stdout becomes the Telegram reply; non-zero exit is an error with stderr surfaced to the user.

### 4.4 Scheduler

- Workers support optional scheduled tasks defined in `hive.toml`.
- Scheduled tasks use cron syntax (via the `cron` key in `[[schedule]]` blocks).
- Scheduled tasks can invoke either a script (via `run`) or an agent run (via `agent_prompt`).

### 4.5 Comb (Web Dashboard)

- Each Worker can optionally expose a Comb — a lightweight web dashboard.
- The Comb is config-driven: workers declare which Cells to display in `hive.toml`. No custom code required per Worker.
- Hive serves all Workers centrally at `localhost:8080/workers/<name>` — local-only, no authentication required.
- MVP Cell types: `log` (tail of a log file), `file` (markdown or plain text), `metric` (single value from a JSON file by key).

Example `hive.toml` dashboard config:

```toml
[comb]
cells = [
  { type = "log",    title = "Recent activity",  source = "logs/worker.log" },
  { type = "file",   title = "Daily summary",    source = "memory/summary.md" },
  { type = "metric", title = "Tasks run today",  source = "memory/stats.json", key = "tasks_today" },
]
```

---

## 5. Process Management

Each Worker runs as a separate OS process. Docker is explicitly out of scope for the initial local version — the isolation benefit does not justify the overhead for a personal tool.

The chosen process manager is **supervisord** — a battle-tested Unix process control system that handles startup, crash recovery, log capture, and a control CLI out of the box.

### 5.1 supervisord

supervisord runs as a background daemon. Each Worker is registered as a program block in `supervisord.conf`. Hive commands (`hive start`, `hive stop`) write or update these blocks and call `supervisorctl` under the hood, so the user always interacts with Hive rather than supervisord directly.

- `autorestart=true` means crashed Workers are automatically restarted.
- Logs are written to the Worker's own `logs/` folder, keeping everything self-contained.
- `hive init` writes the supervisord block automatically and runs `supervisorctl reread` + `supervisorctl update` to register the Worker.

### 5.2 Auto-start on Boot — macOS LaunchAgents

To start supervisord automatically on user login, a launchd plist is placed in `~/Library/LaunchAgents/`. This means all Workers with `autostart=true` are running whenever the machine is on and the user is logged in.

- LaunchAgents triggers on user login, not at boot — no sudo required, correct for a personal local tool.
- `hive init` installs the plist automatically on first use.

---

## 6. Scaffolding — `hive init`

Running `hive init <name>` scaffolds a new Worker:

- Creates the standard folder structure.
- Initialises a git repo.
- Creates a `.venv` with base requirements.
- Generates `hive.toml` and `.env` templates.
- Writes the supervisord program block and reloads supervisord.
- Installs the macOS LaunchAgent on first use.

---

## 7. Configuration — `hive.toml`

Each Worker is configured via a `hive.toml` file in its root. Secrets (bot token, allowed user ID) live in `.env`, not here — `hive.toml` is safe to commit.

```toml
[worker]
name = "my-worker"

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
  { type = "log", title = "Activity", source = "logs/worker.log" }
]
```

---

_This document describes what Hive is and why it is designed this way. For implementation detail — data flows, config schemas, CLI internals, supervisord setup — see `docs/plans/2026-03-09-hive-architecture-design.md`._
