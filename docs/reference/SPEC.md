# Hive

**Project Specification — v0.4**
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

Worker folder structure and the two-layer model diagram: see [`architecture.md`](architecture.md).

### 3.2 Worker as Brain

The Worker is not the agent. The Worker is an event loop that runs continuously, routing messages, firing scripts, and managing state. The Agent is one subsystem of the Worker — invoked only when a task requires LLM reasoning. Routine commands run as plain scripts without touching the LLM.

---

## 4. Worker Components

- **Telegram interface** — slash commands route to `commands/` scripts; natural language routes to the agent. Auth via `TELEGRAM_ALLOWED_USER_ID`. See [`../commands/README.md`](../commands/README.md).
- **Agent** — Claude Agent SDK, session-persistent, scoped to the Worker folder. Can self-configure by editing `hive.toml` and `commands/`. See [`../agent/README.md`](../agent/README.md).
- **Commands** — Python scripts in `commands/`, dual-registered as Telegram handlers and agent MCP tools. See [`../commands/README.md`](../commands/README.md).
- **Scheduler** — APScheduler cron jobs running `run` (scripts) or `agent_prompt` tasks. See [`../scheduling/README.md`](../scheduling/README.md).
- **Comb** — Config-driven web dashboard. See [`../dashboard/README.md`](../dashboard/README.md).

**Why Claude Agent SDK?** It runs on the existing Claude Code installation and inherits its authentication — no API key or separate billing required for personal local use. The SDK provides built-in filesystem tools (`Read`, `Write`, `Bash`, `Glob`), a `cwd` parameter to scope the agent to the Worker's folder (mapping directly onto "one folder = one world"), and supports in-process MCP servers for registering `commands/` scripts as agent tools.

Configuration reference: [`../config/README.md`](../config/README.md). CLI reference: [`../cli/README.md`](../cli/README.md).

---

## 5. Process Management

Each Worker runs as a separate OS process. Docker is explicitly out of scope for the initial local version — the isolation benefit does not justify the overhead for a personal tool.

The chosen process manager is **supervisord** — a battle-tested Unix process control system that handles startup, crash recovery, log capture, and a control CLI out of the box.

- `autorestart=true` means crashed Workers are automatically restarted.
- Logs are written to the Worker's own `logs/` folder, keeping everything self-contained.
- `hive init` writes the supervisord block automatically and runs `supervisorctl reread` + `supervisorctl update`.

**Auto-start on boot** uses a macOS LaunchAgent at `~/Library/LaunchAgents/com.hive.supervisord.plist`. LaunchAgents trigger on user login, not at boot — no sudo required, correct for a personal local tool. Installed automatically on first `hive init`.

Implementation detail: [`architecture.md`](architecture.md).
