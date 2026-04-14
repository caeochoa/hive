---
name: add-command
description: "Add a new command script to an existing Hive Worker. Reads the Worker's current setup for style consistency, then generates a properly formatted command script with YAML docstring, argparse, and stdout/stderr handling. Use when: add command, new command, create command, add script, new script, add /command, I want a command that, add a bot command."
---

# Add a Command to a Hive Worker

You are adding a new command script to an existing Hive Worker. Commands are Python files in `commands/` that become both Telegram slash commands (e.g. `/summarise`) and agent tools via MCP.

Your job is to understand what the command should do, then write a script that fits naturally alongside the Worker's existing commands.

## How commands work (essential context)

Hive discovers all `*.py` files in `commands/` at startup and registers them automatically. Each script must have a YAML docstring at the top:

```python
"""
name: command_name
description: What this command does — shown in /help and as the agent tool description
args:
  - name: arg_name
    type: str       # str, int, float, or bool
    description: What this argument does
    default: value  # omit to make the argument required
"""
```

**Execution contract:**
- Run as: `.venv/bin/python commands/script.py --arg_name value`
- `bool` args are passed as flags (`--flag`, no value); all others as `--name value`
- **Always use named `--argname` flags in argparse** — positional arguments will fail
- stdout → Telegram reply
- Non-zero exit → error (stderr shown to user)
- `WORKER_DIR` env var → absolute path to the Worker folder

**Minimal command template:**

```python
"""
name: example
description: Does something useful
args:
  - name: target
    type: str
    description: What to act on
"""
import argparse
import os
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    worker_dir = Path(os.environ["WORKER_DIR"])

    # ... do something ...

    print("Done.")

if __name__ == "__main__":
    main()
```

**Testing a command in isolation:**

```bash
WORKER_DIR=$(pwd) .venv/bin/python commands/script.py --arg_name value
```

## Step 1: Read the existing Worker

Before writing anything, understand what the Worker already does:

1. Read `hive.toml` — Worker name, agent model, system prompt, schedules
2. Read existing scripts in `commands/` — understand the style, what data structures they use, what files they read/write in `memory/`
3. Note any shared patterns (e.g. all commands read from a specific JSON file, all write to `memory/log.md`)

The goal: write a command that feels like it belongs, not a foreign insertion.

## Step 2: Clarify the command

Ask the user (or infer from context) what the command should do. You need to know:

- **What does it do?** The core action
- **What arguments does it need?** Zero is fine — many useful commands take no args
- **What should it output?** Text that goes to Telegram
- **Does it need to read or write any files?**
- **Does it need third-party packages?**

If the user's description is clear enough, propose the command name, description, and args before writing — confirm once rather than iterate.

## Step 3: Write the command script

Create `commands/<name>.py`. The script must:

1. Start with the YAML docstring (name, description, args)
2. Use `argparse` with `--argname` named flags matching the docstring
3. Print all output to stdout — this is the Telegram reply
4. Use `sys.exit(1)` + `print(..., file=sys.stderr)` for errors
5. Access Worker files via `Path(os.environ["WORKER_DIR"])`
6. Be self-contained — no shared utility modules unless they already exist in the Worker

If the Worker has existing data structures in `memory/` (JSON files, markdown), read and write them consistently with how other commands do.

If the command needs third-party packages, add them to `requirements.txt` and tell the user:

```bash
.venv/bin/pip install -r requirements.txt
```

## Step 4: Confirm and test

After writing the script:

1. Show the user the command name and what it does
2. Give the test invocation they can run to verify it works:
   ```bash
   WORKER_DIR=$(pwd) .venv/bin/python commands/<name>.py --arg value
   ```
3. Note that the Worker must be restarted for the new command to register:
   ```bash
   hive restart ./<worker-name>
   ```
   Or if it's not running yet, `hive start ./<worker-name>`.

## Important guidelines

- **Match existing style.** If all other commands use `json.dumps` for output, do the same. If they use a particular error message format, follow it.
- **Respect existing data structures.** Don't create a new JSON schema if there's already one in `memory/` that fits.
- **Keep it simple.** A command that does one thing well is better than one that tries to do three. The agent can combine multiple commands.
- **Don't add docstrings or comments beyond what's necessary.** The YAML docstring is required; inline comments are only needed where logic isn't obvious.
