# Creating a Worker

This guide walks you through creating a Hive Worker from scratch — starting with the minimum viable setup and layering on features progressively.

> See also: [Feature Guide](../features.md) — a full capability reference once you have a Worker running.

## Prerequisites

- **Hive installed** — clone the repo and run `uv sync` from the project root
- **A Telegram bot token** — create one via [BotFather](https://t.me/BotFather) (`/newbot`)
- **Your Telegram user ID** — send `/start` to [@userinfobot](https://t.me/userinfobot) to get it

## 1. Create a basic Worker

Scaffold a new Worker folder:

```bash
hive init my-worker
```

This creates the following structure:

```
my-worker/
├── .env                 # Secrets (git-ignored)
├── .gitignore           # Pre-configured ignores
├── .venv/               # Isolated Python environment
├── hive.toml            # Worker configuration
├── requirements.txt     # Worker-specific dependencies
├── commands/            # Command scripts
├── dashboard/           # Comb dashboard files
├── logs/                # Runtime logs (git-ignored)
└── memory/              # Agent persistent state
```

The folder is also git-initialized, registered with supervisord, and given its own `.venv`.

On first use, `hive init` also installs a macOS LaunchAgent so supervisord starts automatically on login.

### Configure secrets

Edit `my-worker/.env` and fill in your credentials:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USER_ID=987654321
```

Both values are required — the Worker will not start without them.

### Start the Worker

```bash
hive start ./my-worker
```

Open Telegram and send a message to your bot. Natural language messages are routed to the Claude agent. Try sending:

- A plain message like "What can you do?" — goes to the agent
- `/help` — lists all available commands
- `/reset` — clears the conversation and starts a fresh session

### Manage the Worker

```bash
hive status               # Show status of all Workers
hive logs ./my-worker     # Tail the last 50 lines of logs
hive logs ./my-worker -f  # Follow logs in real time
hive logs ./my-worker -n 100  # Show last 100 lines
hive stop ./my-worker     # Stop the Worker
hive restart ./my-worker  # Restart the Worker
```

## 2. Add a command script

Commands are Python scripts in the `commands/` folder. Each script has a YAML docstring that defines its metadata.

Create `my-worker/commands/hello.py`:

```python
"""
name: hello
description: Say hello
"""

print("Hello from my first command!")
```

Every command script needs at minimum:

- **`name`** — the command name (used as `/hello` in Telegram and as a tool name for the agent)
- **`description`** — a short description shown in `/help` and exposed to the agent

### Execution contract

- Hive runs scripts as: `.venv/bin/python commands/hello.py`
- **stdout** is sent back as the Telegram reply
- **Non-zero exit code** means an error occurred — stderr is surfaced to the user
- The `WORKER_DIR` environment variable is set to the Worker folder path, so scripts can access Worker files

Restart the Worker to pick up the new command:

```bash
hive restart ./my-worker
```

Now send `/hello` in Telegram. The agent can also call this command as a tool during conversations.

> See also: [Commands reference](../commands/README.md)

## 3. Add a command with arguments

Commands can accept typed arguments with defaults. Create `my-worker/commands/greet.py`:

```python
"""
name: greet
description: Greet someone by name
args:
  - name: person
    type: str
    description: Name of the person to greet
  - name: times
    type: int
    description: Number of times to greet
    default: 1
"""

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--person", required=True)
parser.add_argument("--times", type=int, default=1)
args = parser.parse_args()

for _ in range(args.times):
    print(f"Hello, {args.person}!")
```

### Metadata fields for args

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Argument name |
| `type` | Yes | One of: `str`, `int`, `float`, `bool` |
| `description` | Yes | What the argument does |
| `default` | No | Default value. If omitted, the argument is required |

### How arguments are passed

- **As a subprocess:** args are passed as CLI flags — `--person Alice --times 3`
- **In Telegram:** args are positional — `/greet Alice 3`
- **As an agent tool:** args are passed as a JSON object matching the schema

### Error handling

If a script exits with a non-zero code, Hive sends the stderr output as an error reply. Use `sys.exit(1)` and `print("message", file=sys.stderr)` for controlled error reporting:

```python
import sys

if not valid:
    print("Invalid input", file=sys.stderr)
    sys.exit(1)
```

## 4. Configure the agent

Edit the `[agent]` section in `my-worker/hive.toml`:

```toml
[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
system_prompt = "You are a personal assistant. Keep responses concise."
```

| Field | Default | Description |
|---|---|---|
| `model` | `claude-haiku-4-5` | Claude model to use |
| `memory_dir` | `memory/` | Directory for agent persistent state |
| `max_turns` | `10` | Maximum agent turns per conversation |
| `system_prompt` | `"You are a worker agent. Your world is this folder."` | Custom system prompt |

### Memory

The `memory/` directory is the agent's persistent state store. The agent can read and write files here across sessions. Use it for summaries, notes, preferences, or any data the agent should remember.

Agent sessions are tracked per Telegram chat ID, with session state stored in `memory/.sessions.json`.

> See also: [Agent reference](../agent/README.md)

### Auto-commit

After every agent turn, Hive automatically commits any changes to these tracked paths in the Worker's git repo:

- `commands/`
- `memory/`
- `hive.toml`
- `dashboard/`

Commit messages follow the format: `hive: auto-commit after <reason>`.

## 5. Add scheduled tasks

Add `[[schedule]]` blocks to `my-worker/hive.toml`. There are two types:

### Run a script on a schedule

```toml
[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"
```

### Run an agent prompt on a schedule

```toml
[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"
```

Each schedule entry requires `cron` and exactly one of `run` or `agent_prompt`.

> See also: [Scheduling reference](../scheduling/README.md)

### Cron syntax examples

| Cron | Meaning |
|---|---|
| `0 8 * * *` | Every day at 8:00 AM |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 0 1 * *` | First day of every month at midnight |

## 6. Add a Comb dashboard

Add `[comb]` configuration to `my-worker/hive.toml`:

```toml
[comb]
cells = [
  { type = "log",    title = "Activity",    source = "logs/out.log" },
  { type = "file",   title = "Summary",     source = "memory/summary.md" },
  { type = "metric", title = "Tasks today", source = "memory/stats.json", key = "tasks_today" },
]
```

### Cell types

| Type | Renders | Required fields |
|---|---|---|
| `log` | Tail of a log file, auto-refreshing | `type`, `title`, `source` |
| `file` | Markdown or plain text file | `type`, `title`, `source` |
| `metric` | Single value extracted from a JSON file | `type`, `title`, `source`, `key` |

Start the dashboard server:

```bash
hive comb
```

View your Worker's dashboard at `http://localhost:8080/workers/my-worker`.

By default the server binds to `127.0.0.1:8080`. Use `--host` and `--port` to override.

> See also: [Dashboard reference](../dashboard/README.md)

## 7. Reference

### Full `hive.toml` example

```toml
[worker]
name = "my-worker"

[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
system_prompt = "You are a personal assistant. Keep responses concise."

[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"

[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"

[comb]
cells = [
  { type = "log",    title = "Activity",    source = "logs/out.log" },
  { type = "file",   title = "Summary",     source = "memory/summary.md" },
  { type = "metric", title = "Tasks today", source = "memory/stats.json", key = "tasks_today" },
]
```

### `.env` reference

```
TELEGRAM_BOT_TOKEN=<your bot token from BotFather>
TELEGRAM_ALLOWED_USER_ID=<your numeric Telegram user ID>
```

Both values are required. The `.env` file is git-ignored by default.

### CLI command summary

| Command | Description |
|---|---|
| `hive init <name>` | Scaffold a new Worker folder, git init, create .venv, register with supervisord |
| `hive start <path>` | Start a Worker process via supervisord |
| `hive stop <path>` | Stop a Worker process |
| `hive restart <path>` | Restart a Worker process |
| `hive remove <path>` | Unregister a Worker (add `--delete` to also remove the folder) |
| `hive status` | Show status of all Workers |
| `hive logs <path>` | Tail Worker logs (`-n` for line count, `-f` to follow) |
| `hive run <path>` | Internal — Worker entrypoint called by supervisord |
| `hive comb` | Start the Comb dashboard server (`--host`, `--port` to override) |

### Command script docstring format

```python
"""
name: command_name
description: What this command does
args:
  - name: arg_name
    type: str          # str, int, float, or bool
    description: What this argument does
    default: value     # optional — omit to make the argument required
"""
```
