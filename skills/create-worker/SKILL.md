---
name: create-worker
description: "Create a new Hive Worker — a purpose-built Telegram bot powered by Claude. Guides through scaffolding, configuration, command scripts, schedules, and dashboard setup. Analyzes existing code in the directory to generate tailored commands. Use when: create worker, new worker, init worker, set up a bot, make a telegram bot with hive, scaffold worker, hive init, build a worker, I want a bot that, turn this into a worker."
---

# Create a Hive Worker

You are creating a Hive Worker — a purpose-built Telegram bot backed by Claude as an AI agent. Workers live in self-contained folders with config, command scripts, memory, and logs. Hive provides the runtime infrastructure.

Your job is to understand what the user wants their Worker to do, then generate a complete, tailored Worker setup — not a generic scaffold.

## How Workers work (essential context)

A Worker folder looks like this after `hive init`:

```
my-worker/
├── .env                 # Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
├── .gitignore
├── .venv/               # Isolated Python env for command scripts
├── hive.toml            # All config: worker name, agent settings, schedules, dashboard
├── requirements.txt     # Worker-specific pip dependencies
├── commands/            # Python scripts — each becomes a /command AND an agent tool
├── dashboard/           # Comb dashboard files
├── logs/                # Runtime logs (git-ignored)
└── memory/              # Agent's persistent read/write state
```

**Message routing:** Natural language messages go to the Claude agent. Slash commands go to scripts in `commands/`. Built-in commands: `/help` (lists all commands), `/menu` (interactive command picker), `/reset` (clears agent session), `/set` (runtime session overrides — change model, max_turns, or thinking_budget_tokens per-chat without restarting).

**Command scripts** are Python files with a YAML docstring:

```python
"""
name: command_name
description: What this command does
args:
  - name: arg_name
    type: str       # str, int, float, or bool
    description: What this argument does
    default: value  # omit to make required
"""
```

Execution contract:
- Run as: `.venv/bin/python commands/script.py --arg_name value`
- stdout → Telegram reply
- Non-zero exit → error (stderr shown to user)
- `WORKER_DIR` env var → path to the Worker folder
- Commands are also exposed to the agent as tools via MCP

**Config (`hive.toml`):**

```toml
[worker]
name = "worker-name"

[agent]
model = "claude-haiku-4-5"          # default
memory_dir = "memory/"               # default
max_turns = 10                       # default
system_prompt = "..."                # optional; disables self-config instructions if set
# thinking_budget_tokens = 5000      # optional; enables extended thinking

[[schedule]]
cron = "0 8 * * *"
run = "commands/script.py"           # OR agent_prompt = "Do something"
# skip_if_five_hour_above = 0.50     # optional; skip if 5-hour usage exceeds this USD threshold
# skip_if_seven_day_above = 5.00     # optional; skip if 7-day usage exceeds this USD threshold
# notify_on_skip = true              # optional; send Telegram message when job is skipped (default true)

[comb]
# theme = "dark"                     # optional dashboard theme
cells = [
  { type = "log",      title = "...", source = "logs/out.log" },
  { type = "file",     title = "...", source = "memory/notes.txt" },
  { type = "markdown", title = "...", source = "memory/summary.md" },
  { type = "metric",   title = "...", source = "memory/stats.json", key = "key_name" },
  { type = "status",   title = "...", source = "memory/health.json", key = "status" },
  { type = "table",    title = "...", source = "memory/items.json" },
  { type = "chart",    title = "...", source = "memory/data.json", key = "values" },
  # { type = "app", title = "...", source = "dashboard/custom.py" }  # full FastAPI router — only Hive env packages available, not the Worker's .venv
]
```

**Secrets (`.env`):**
```
TELEGRAM_BOT_TOKEN=<from BotFather>
TELEGRAM_ALLOWED_USER_ID=<numeric user ID>   # comma-separate for multiple users: 12345,67890
```

Both are required. The Worker won't start without them.

**Auto-commit:** After every agent turn, Hive auto-commits changes to `commands/`, `memory/`, `hive.toml`, and `dashboard/`.

**Worker self-configuration:** The agent can edit `hive.toml` and `commands/` files to reconfigure itself. Hive detects the changes and schedules a graceful restart — no manual intervention needed.

## Step 1: Understand the context

Before asking questions, look at what's already in the current directory:

1. **Read the directory listing** — `ls -la` to see what exists
2. **If there's existing code** (Python files, data files, configs), read the key files to understand what the project does. This context shapes everything — the Worker name, its commands, its system prompt, what schedules make sense.
3. **If the directory is empty or has only basic files**, you'll rely more on the user interview.

The goal: by the end of this step, you should have a mental model of what this Worker is about, even before asking questions.

## Step 2: Interview the user

Ask targeted questions based on what you found. Don't ask about things you can already infer from the code. Keep it conversational — 3-5 questions max in a single message.

What you need to know:

- **What should this Worker do?** (if not obvious from the code)
- **What commands should it have?** Suggest specific ones based on the code you read. For example: "I see you have budget tracking logic — should I create `/add_expense`, `/summary`, and `/report` commands?"
- **Should it run anything on a schedule?** Suggest based on context (daily summaries, weekly reports, periodic data fetches).
- **What should the agent's personality/focus be?** This becomes the system prompt. If the code context is strong enough, propose one.
- **Do they have their Telegram bot token and user ID ready?**

Don't ask about things that have sensible defaults (model, max_turns, memory_dir) unless the user brings them up.

## Step 3: Scaffold the Worker

Run `hive init <name>` where `<name>` comes from the interview or the directory context.

If the user is already in the directory where the Worker should live, and it's not inside the Hive repo, `hive init .` won't work — the name comes from the argument, and `hive init` creates a subdirectory. Clarify with the user whether they want the Worker as a subdirectory or if they want to scaffold in the current directory (in which case you'll create the files manually following the same structure `hive init` would produce).

After scaffolding, remind the user to fill in `.env` with their bot token and user ID.

## Step 4: Configure `hive.toml`

Edit the generated `hive.toml` to include:

- A tailored `system_prompt` in `[agent]` that reflects what this Worker does. Be specific — "You are a budget tracking assistant. You help the user log expenses, categorize spending, and generate financial summaries. You store all data in memory/." is much better than "You are a helpful assistant."
- `[[schedule]]` blocks if the user wants recurring tasks
- `[comb]` cells if the user wants a dashboard

## Step 5: Create command scripts

This is where the skill earns its keep. Generate command scripts that are genuinely useful, not hello-world examples.

Each command script must:
1. Start with the YAML docstring (name, description, args)
2. Use `argparse` to parse `--arg value` flags matching the docstring args
3. Print output to stdout (this becomes the Telegram reply)
4. Use `sys.exit(1)` and `print(..., file=sys.stderr)` for errors
5. Access Worker files via `os.environ["WORKER_DIR"]` when needed

If the directory has existing Python code, look at what it does and wrap that logic into command scripts. Import from or call the existing code rather than rewriting it — the command script is a thin CLI wrapper.

If the command needs third-party packages, add them to `requirements.txt` and remind the user to install them: `.venv/bin/pip install -r requirements.txt`

## Step 6: Verify and start

After generating everything:

1. List what was created and explain each piece briefly
2. Remind the user to:
   - Fill in `.env` if they haven't
   - Install any requirements: `.venv/bin/pip install -r requirements.txt`
   - Start the Worker: `hive start ./<worker-name>`
   - Apply config changes later with: `hive restart ./<worker-name>`
3. Suggest testing:
   - **Without Telegram:** `hive chat ./<worker-name>` — interactive TUI, supports all commands and agent messages
   - **With Telegram:** Send a message to your bot and try `/help` to see your commands

## Important guidelines

- **Don't over-scaffold.** Only create commands, schedules, and dashboard cells that the user actually needs. An empty `commands/` folder is fine if the user only wants the agent.
- **Match the user's domain language.** If they're building a fitness tracker, use fitness terminology in the system prompt and command descriptions. If they're building a devops bot, use ops terminology.
- **Command scripts should be self-contained.** Each script should work independently — don't create shared utility modules unless there's a compelling reason. The Worker's `.venv` is isolated, so scripts can import anything installed there.
- **Prefer `memory/` for persistence.** Command scripts and the agent both have access to `memory/`. Use JSON files for structured data and markdown files for human-readable state.
- **Keep the system prompt focused.** Tell the agent what it is, what it has access to, and how it should behave. Don't try to encode business logic in the prompt — that's what command scripts are for.
