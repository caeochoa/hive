# Hive Architecture

_Last updated: 2026-03-27_

---

## 1. Two-Layer Model

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

Each `hive run <path>` process runs a single async event loop with four subsystems: Telegram handler, agent runner, scheduler, and auto-committer.

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
      │  subprocess │  │  (session-aware)  │
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

**Scheduler** (APScheduler) runs as a parallel async task in the same process, firing scripts or agent prompts on cron schedule. supervisord's `autorestart=true` handles crash recovery for the whole process.

Command system detail: [`../commands/README.md`](../commands/README.md). Agent detail: [`../agent/README.md`](../agent/README.md). Scheduling detail: [`../scheduling/README.md`](../scheduling/README.md).

---

## 3. Built-in Commands

Present on every Worker regardless of `commands/` contents. Not exposed as agent tools — they control the runtime, not the Worker's domain logic. Built-in handlers are registered before user-defined commands and take precedence if names conflict.

| Command | What it does |
|---|---|
| `/reset` | Clears the agent session and all session overrides for the current chat. |
| `/help` | Lists all available commands (built-in + user-defined) with inline keyboard. |
| `/menu` | Compact inline keyboard launcher. |
| `/set` | Runtime config override for the current session. See [`../agent/README.md`](../agent/README.md). |

---

## 4. Agent — Self-Config Edge Cases

Full agent documentation: [`../agent/README.md`](../agent/README.md).

Edge cases not in the component doc:

**Scheduled tasks skip change detection.** Change detection is wired only into the interactive NL message handler (`_handle_nl_message`). Scheduled `agent_prompt` tasks intentionally skip it — to avoid unattended restarts mid-schedule. supervisord will pick up config changes on the next interactive turn.

**Agent error skips restart.** If the agent turn or Telegram message delivery fails, the config snapshot is never taken and no restart fires — even if `hive.toml` or `commands/*.py` were modified. This is intentional: if delivery couldn't be confirmed, the worker treats the turn as inconclusive.

---

## 5. Process Management

### supervisord program block

Each Worker is registered as:

```ini
[program:worker-<name>]
command=hive run /path/to/worker
directory=/path/to/worker
autostart=true
autorestart=true
stdout_logfile=/path/to/worker/logs/out.log
stderr_logfile=/path/to/worker/logs/err.log
```

Written by `hive start`; removed by `hive remove`. Reloaded via `supervisorctl reread && supervisorctl update`.

### macOS LaunchAgent

supervisord itself starts on user login via `~/Library/LaunchAgents/com.hive.supervisord.plist`. Installed once during `hive init` on first use, alongside the Comb supervisord block.

CLI reference: [`../cli/README.md`](../cli/README.md).

---

## 6. Worker Folder Structure

```
my-worker/
├── .git/                  # All changes auto-committed by Hive
├── .gitignore             # Ignores .env, .venv/, logs/, *.pyc, __pycache__/
├── .venv/                 # Scripts-only venv (not for Hive itself)
├── .env                   # Secrets (git-ignored)
├── hive.toml              # Worker config
├── commands/              # Scripts = bot commands = agent tools
│   ├── summarise.py
│   └── fetch_news.py
├── memory/                # Agent state, notes, working memory
│   └── .sessions.json     # Per-chat session IDs (auto-managed)
├── logs/                  # Worker output (written by supervisord)
└── dashboard/             # Optional static assets for the Comb
```

Auto-commit scope: `commands/`, `memory/`, `hive.toml`, `dashboard/`. Logs and `.venv` are never committed.
