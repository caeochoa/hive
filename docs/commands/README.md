# Commands

Commands are Python scripts in a Worker's `commands/` folder. Each script is dual-purpose: it is registered as a Telegram slash command (e.g., `/status`) and simultaneously exposed as a tool the Claude agent can call. Hive discovers and wires up both at startup with no additional configuration.

## Docstring format

Every command script must begin with a triple-quoted docstring containing YAML metadata. This is how Hive learns the command's name, description, and arguments.

```python
"""
name: status
description: Show current status summary
args:
  - name: verbose
    type: bool
    description: Include extra detail
  - name: limit
    type: int
    description: Maximum number of items to show
    default: 5
"""
```

Required fields:

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Command name, used as the Telegram slash command and MCP tool name |
| `description` | Yes | Human-readable description shown in `/help` and agent tool listings |
| `args` | No | List of argument definitions (see below) |

Each entry under `args`:

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Argument name |
| `type` | Yes | One of `str`, `int`, `float`, `bool` |
| `description` | Yes | Description shown to the agent |
| `default` | No | Default value if the argument is not provided |

An argument without a `default` is treated as required.

## Argument types and CLI mapping

When Hive invokes a script as a subprocess, arguments are passed on the command line:

| Type | Invocation style | Example |
|---|---|---|
| `str` | `--name value` | `--query "hello world"` |
| `int` | `--name value` | `--limit 10` |
| `float` | `--name value` | `--threshold 0.75` |
| `bool` | `--name` (flag only, no value) | `--verbose` |

A `bool` argument is only appended to the command line when its value is truthy. If false, the flag is omitted entirely.

## Shebang line handling

If a script's first line starts with `#!`, Hive skips it before parsing the docstring. This means shebangs are allowed and will not break docstring detection:

```python
#!/usr/bin/env python3
"""
name: my-command
description: Works fine with a shebang
"""
```

## Execution contract

- **Interpreter:** `.venv/bin/python` inside the Worker folder. The Worker's virtualenv is used, not the system Python or Hive's environment.
- **Stdout:** Sent as the Telegram reply (and returned to the agent as tool output).
- **Stderr:** Surfaced to the user as an error message when the exit code is non-zero.
- **Exit code:** Any non-zero exit code is treated as an error. The script's stderr is forwarded to the user.
- **WORKER_DIR:** Set as an environment variable on every invocation. Scripts use this to locate files within the Worker folder (e.g., `os.environ["WORKER_DIR"] + "/memory/data.json"`).

## Agent tool wiring

At startup, `CommandRegistry.build_mcp_server()` creates an in-process MCP server and registers each discovered command as a tool. The agent receives:

- Tool name: the command's `name` field
- Tool description: the command's `description` field
- Input schema: derived from `args` (JSON Schema, with `required` populated for args without defaults)

The agent calls commands via the same `execute()` path as Telegram handlers. Default values for optional args are applied before execution.

## Discovery

Hive calls `CommandRegistry.discover()` at Worker startup. It globs `commands/*.py` (sorted alphabetically), parses each file's docstring, and registers valid commands. Scripts with missing or malformed docstrings are skipped with a warning log; they do not prevent other commands from loading.

## Complete example

`commands/status.py` — reads a summary file from memory and returns it:

```python
"""
name: status
description: Show the current status summary from memory
args:
  - name: lines
    type: int
    description: Number of lines to show
    default: 20
"""

import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--lines", type=int, default=20)
args = parser.parse_args()

worker_dir = Path(os.environ["WORKER_DIR"])
summary = worker_dir / "memory" / "summary.md"

if not summary.exists():
    print("No summary found.")
else:
    lines = summary.read_text().splitlines()
    print("\n".join(lines[: args.lines]))
```

In Telegram: `/status` or `/status 50`

As an agent tool call: `status` with optional `{"lines": 50}`

## Testing a command in isolation

Run directly from the Worker folder without starting the full bot:

```bash
.venv/bin/python commands/status.py --lines 10
```

For bool flags:

```bash
.venv/bin/python commands/status.py --verbose
```

Set `WORKER_DIR` manually if the script reads from the Worker folder:

```bash
WORKER_DIR=$(pwd) .venv/bin/python commands/status.py --lines 10
```

## Troubleshooting

If a command isn't appearing in `/help` or isn't available as an agent tool, see [Troubleshooting → Command not appearing](../guides/troubleshooting.md#command-not-appearing-in-help-or-not-working).
