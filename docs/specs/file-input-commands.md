# `file_input` Commands — Accept Telegram Document Attachments

## Motivation

Some Worker tasks require receiving a file from the user — uploading a bank CSV export, submitting a document for analysis, attaching a photo. The current command model handles only text arguments. There is no way for a command to declare that it expects a file, and no mechanism for Hive to route an incoming document message to a pending command.

This spec proposes a `file_input: true` flag for command YAML docstrings, with the associated runtime changes to wire it up.

---

## Proposed API

A command opts in by adding `file_input: true` to its YAML docstring. This is the only change required in the command script itself.

```yaml
name: upload-transactions
description: Save a bank CSV export to bank_exports/ for review
args:
  - name: account
    type: str
    description: "Account type: checking or card"
file_input: true
```

When `file_input: true` is present, the command's normal text arguments work as before. The file is delivered as an additional `--file <absolute_path>` argument after all other args.

---

## User Experience

```
User:  /upload-transactions checking
Bot:   Please attach a file.
User:  [attaches Movimientos_5_1_2026.csv]
Bot:   Saved to bank_exports/bankinter-checking/Movimientos_5_1_2026.csv
```

The command can also be invoked by the agent, which then prompts the user for the attachment on the command's behalf.

---

## Runtime Behaviour

1. User invokes a `file_input` command (via slash command or agent tool call).
2. Hive detects `file_input: true` on the command. Instead of executing immediately, it stores a **pending upload state** for the user and replies *"Please attach a file."*
3. The next `Document` message from that user triggers execution:
   - Hive downloads the file to a temp path.
   - Appends `--file <path>` to the collected args.
   - Executes the command script.
   - Clears the pending state.
4. Script stdout is sent as the Telegram reply, as normal.

---

## Pending State Lifecycle

| Trigger | Action |
|---|---|
| Document received | Execute command, clear state |
| Text message while pending | Cancel pending state, notify user: *"Upload cancelled."* |
| 5-minute timeout | Clear state, notify user: *"Upload timed out. Please run the command again."* |

Pending state is stored in-memory, keyed by `(chat_id, user_id)` — the same scope as session overrides. It does not persist across Worker restarts.

---

## Script Contract

Scripts with `file_input: true` receive `--file <absolute_path>` as an additional CLI argument. The file is a temporary path; the script is responsible for moving or processing it. Hive does not clean up the temp file — the script should handle that if needed.

```python
parser.add_argument("--file", required=True, help="Path to the uploaded file")
```

---

## Implementation Checklist

Changes required in `src/hive/worker/`:

1. **`commands.py`** (`CommandRegistry` / command model) — parse `file_input` from YAML; expose it as a boolean field on the command model (default `False`).
2. **`runtime.py`** — command dispatcher: if `file_input` is `True`, store pending state `{(chat_id, user_id) → {command, collected_args}}` and send *"Please attach a file."* instead of executing.
3. **`runtime.py`** — new `MessageHandler(filters.Document.ALL, ...)`: look up pending state for the user; if found, download the file, append `--file`, and execute; if not found, fall through to the agent.
4. **`runtime.py`** — pending state timeout: schedule a one-shot APScheduler job (already a dependency) for 5 minutes after the state is parked; on fire, clear state and notify.

---

## Example Worker Command

`commands/upload-transactions.py` for the budget-bot Worker:

```python
#!/usr/bin/env python3
"""
name: upload-transactions
description: Save a bank CSV export to bank_exports/ for review
args:
  - name: account
    type: str
    description: "Account type: checking or card"
file_input: true
"""

import argparse
import os
import shutil
from pathlib import Path

VALID_ACCOUNTS = {"checking", "card"}

parser = argparse.ArgumentParser()
parser.add_argument("--account", required=True)
parser.add_argument("--file", required=True)
args = parser.parse_args()

if args.account not in VALID_ACCOUNTS:
    print(f"Error: account must be one of: {', '.join(VALID_ACCOUNTS)}")
    raise SystemExit(1)

worker_dir = Path(os.environ["WORKER_DIR"])
dest_dir = worker_dir / "bank_exports" / f"bankinter-{args.account}"
dest_dir.mkdir(parents=True, exist_ok=True)

src = Path(args.file)
dest = dest_dir / src.name
shutil.move(str(src), dest)

print(f"Saved to bank_exports/bankinter-{args.account}/{src.name}")
```
