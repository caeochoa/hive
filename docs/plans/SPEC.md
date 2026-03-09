# 🐝 Hive

**Project Specification — Draft v0.1**
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

> ⚠ Command discovery and registration mechanism to be defined — likely auto-discovered from `commands/` at startup.
> ⚠ Authentication / access control for the Telegram bot (who can send commands?) to be defined.

### 4.2 Agent

- An LLM agent runs inside each Worker, invoked on demand.
- The agent has access to the Worker's folder as its memory and state.
- The agent's tools are auto-discovered from the `commands/` folder. Each script exposes a metadata block (description, args schema) that the Worker registers at startup.
- The git repo acts as an audit trail for all agent writes to the folder.

**Decision: the agent is powered by the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)** (`pip install claude-agent-sdk`). It runs on the existing Claude Code installation and inherits its authentication — no API key or separate billing required for personal local use. The SDK provides built-in filesystem tools (`Read`, `Write`, `Bash`, `Glob`) and supports a `cwd` parameter to scope the agent to the Worker's folder, which maps directly onto the "one folder = one world" design. Custom tools are registered as in-process MCP servers, which is how `commands/` scripts will be exposed to the agent.

Example invocation:

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt="You are a worker agent. Your world is this folder.",
    allowed_tools=["Read", "Write", "Bash", "Glob"],
    permission_mode="acceptEdits",
    cwd="/path/to/worker-folder",
    mcp_servers={"commands": commands_mcp_server},  # auto-discovered from commands/
)

async for message in query(prompt=task, options=options):
    ...
```

> ⚠ Memory strategy: how does the agent read/write to `memory/`? Free-form files, structured store, or both?
> ⚠ Whether the agent can commit to git itself, or whether commits are always triggered by Hive.

### 4.3 Commands

- Scripts in `commands/` serve as both bot commands (user-facing) and agent tools (LLM-facing).
- Each script exposes a metadata block — name, description, args — used for both Telegram command registration and agent tool schema generation.
- Scripts run inside the Worker's `.venv`, allowing per-worker dependencies.

> ⚠ Metadata format to be defined (docstring convention, YAML header, or separate manifest file).
> ⚠ Stdin/stdout contract between Hive and scripts to be defined.

### 4.4 Scheduler

- Workers support optional scheduled tasks defined in `hive.toml`.
- Scheduled tasks can invoke either a script (command) or an agent run.

> ⚠ Cron syntax vs interval-based scheduling to be decided.
> ⚠ How scheduled agent runs are prompted (what message/task is passed to the agent).

### 4.5 Comb (Web Dashboard)

- Each Worker can optionally expose a Comb — a lightweight web dashboard.
- The Comb is config-driven: workers declare which Cells to display in `hive.toml`. No custom code required per Worker.
- Hive ships a standard set of Cell types.

Example `hive.toml` dashboard config:

```toml
[comb]
cells = [
  { type = "log",    title = "Recent activity",  source = "logs/worker.log" },
  { type = "file",   title = "Daily summary",    source = "memory/summary.md" },
  { type = "metric", title = "Tasks run today",  source = "memory/stats.json", key = "tasks_today" },
]
```

> ⚠ Full list of Cell types to be defined. Candidates: log, markdown file, JSON metric, command trigger button, iframe.
> ⚠ Whether the Comb is served by Hive centrally or by each Worker process.
> ⚠ Authentication for the Comb (local-only vs password-protected).

---

## 5. Process Management

Each Worker runs as a separate OS process. Docker is explicitly out of scope for the initial local version — the isolation benefit does not justify the overhead for a personal tool.

The chosen process manager is **supervisord** — a battle-tested Unix process control system that handles startup, crash recovery, log capture, and a control CLI out of the box. A custom Hive daemon remains a future option if tighter integration is needed, but does not replace supervisord.

### 5.1 supervisord

supervisord runs as a background daemon. Each Worker is registered as a program block in `supervisord.conf`. Hive commands (`hive start`, `hive stop`) write or update these blocks and call `supervisorctl` under the hood, so the user always interacts with Hive rather than supervisord directly.

Example program block for a Worker:

```ini
[program:worker-finance]
command=hive run /home/cesar/hive/workers/finance
directory=/home/cesar/hive/workers/finance
autostart=true
autorestart=true
stdout_logfile=/home/cesar/hive/workers/finance/logs/out.log
stderr_logfile=/home/cesar/hive/workers/finance/logs/err.log
```

Key `supervisorctl` commands:

```bash
supervisorctl status                  # view all workers
supervisorctl start worker-finance
supervisorctl stop worker-finance
supervisorctl restart worker-finance
supervisorctl tail -f worker-finance  # live logs
```

- `autostart=true` means the Worker starts automatically when supervisord starts.
- `autorestart=true` means crashed Workers are automatically restarted.
- Logs are written to the Worker's own `logs/` folder, keeping everything self-contained.

> ⚠ How `hive init` registers a new Worker with supervisord automatically (write config + `supervisorctl reread` + `supervisorctl update`).
> ⚠ Whether `hive start` / `hive stop` are thin wrappers over `supervisorctl` or do additional work.

### 5.2 Auto-start on Boot — macOS LaunchAgents

To start supervisord automatically on user login, a launchd plist is placed in `~/Library/LaunchAgents/`. This means all Workers with `autostart=true` are running whenever the machine is on and the user is logged in.

Plist file: `~/Library/LaunchAgents/com.hive.supervisord.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hive.supervisord</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/supervisord</string>
        <string>-c</string>
        <string>/path/to/supervisord.conf</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Load the plist once after creating it:

```bash
launchctl load ~/Library/LaunchAgents/com.hive.supervisord.plist
```

- LaunchAgents triggers on user login, not at boot. This is intentional — no sudo required, and correct for a personal local tool.
- LaunchDaemons (boot-time, pre-login) is available but out of scope.
- `hive init` should optionally install or update the plist as part of first-time setup.

> ⚠ Exact paths for supervisord binary and conf file to be confirmed at setup time.
> ⚠ Whether `hive init` handles plist installation automatically or documents it as a manual step.

---

## 6. Scaffolding — `hive init`

Running `hive init <name>` (or `hive init` inside an empty folder) should scaffold a new Worker:

- Create the standard folder structure.
- Initialise a git repo.
- Create a `.venv` with base requirements.
- Generate a `hive.toml` template.
- Optionally prompt for Telegram bot token and basic config.

> ⚠ Whether `hive init` also registers and starts the Worker, or if that's a separate step.
> ⚠ Base `requirements.txt` contents for the scripts venv.

---

## 7. Configuration — `hive.toml`

Each Worker is configured via a `hive.toml` file in its root. Sketch of the structure:

```toml
[worker]
name = "my-worker"
telegram_token = "..."

[agent]
memory_dir = "memory/"

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

> ⚠ Full `hive.toml` schema to be defined.
> ⚠ How secrets (API keys, tokens) are handled — env vars, separate secrets file, or system keychain.

---

## 8. Open Questions

> ⚠ Script metadata format (how commands advertise themselves as tools).
> ⚠ Stdin/stdout/exit code contract between Hive and scripts.
> ⚠ How `hive init` registers a new Worker with supervisord (config write + reread + update).
> ⚠ Whether `hive init` installs the LaunchAgents plist automatically or documents it as a manual step.
> ⚠ Comb Cell type inventory.
> ⚠ Comb serving model: centralised vs per-worker.
> ⚠ Authentication for Telegram bots and Comb dashboard.
> ⚠ Secrets management strategy.
> ⚠ Whether the agent can self-commit to git.
> ⚠ Full `hive.toml` schema.
> ⚠ Memory structure inside `memory/` — free-form or structured.

---

_This document is a living spec. ⚠ items are open questions to be resolved during design._
