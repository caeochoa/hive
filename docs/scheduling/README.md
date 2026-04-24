# Scheduling

Workers support cron-scheduled tasks defined in `hive.toml`. Each entry fires independently of Telegram activity. There are two job types: `run` executes a command script, and `agent_prompt` sends a prompt through the Claude agent.

> **Note:** Scheduled jobs do not trigger config reload or auto-restart. If you update `hive.toml` while the Worker is running, use `hive restart <path>` to apply changes manually.


## TOML format

Add one or more `[[schedule]]` tables to `hive.toml`. Each entry requires a `cron` field plus exactly one of `run` or `agent_prompt`.

```toml
[[schedule]]
cron = "0 8 * * *"
run = "commands/morning_brief.py"

[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"
```

## Cron syntax

Five-field standard cron: `minute hour day-of-month month day-of-week`.

| Field | Range |
|---|---|
| minute | 0–59 |
| hour | 0–23 |
| day-of-month | 1–31 |
| month | 1–12 |
| day-of-week | 0–7 (0 and 7 are Sunday) |

Common patterns:

| Expression | Meaning |
|---|---|
| `0 8 * * *` | Every day at 08:00 |
| `0 9 * * 1` | Every Monday at 09:00 |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 1 * *` | First day of every month at midnight |
| `30 17 * * 1-5` | Weekdays at 17:30 |
| `0 */6 * * *` | Every 6 hours |

## `run` jobs

`run` takes a path to a command script (relative to the Worker folder or just the filename).

Behavior:
- Hive matches the value against discovered commands by filename (e.g., `commands/morning_brief.py` matches the script whose file is `morning_brief.py`).
- The script is executed with no arguments. If you need arguments, use `agent_prompt` instead or write the defaults into the script.
- Output is sent to each allowed user via Telegram and also written to the Worker's log.
- If the script exits with a non-zero code, an error message is sent to each allowed user via Telegram.
- After the script completes, Hive auto-commits any modified files in the Worker folder.
- If the command is not found in the registry at startup, the schedule entry is skipped with a warning.

```toml
[[schedule]]
cron = "0 6 * * *"
run = "commands/daily_digest.py"
```

## `agent_prompt` jobs

`agent_prompt` takes a plain-text prompt string.

Behavior:
- The prompt is sent through the Claude agent, using the same agent session infrastructure as regular Telegram messages.
- The agent runs for each allowed user ID configured in `.env`. Each user gets a separate agent invocation and receives the response as a Telegram message.
- The response is sent to each allowed user via Telegram.
- After all users have been processed, Hive auto-commits any modified files.

**Session continuity:** Scheduled `agent_prompt` runs share the same per-user session as interactive Telegram messages. This is intentional — after receiving a scheduled response, you can send follow-up messages in Telegram and the agent will have context from the scheduled run. A separate session-per-schedule-entry design was considered but deferred until session management is revisited more broadly.

```toml
[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"
```

## Usage-aware skipping (not yet functional)

`agent_prompt` jobs accept `skip_if_five_hour_above`, `skip_if_seven_day_above`, and `notify_on_skip` fields, but **these are currently no-ops**. The Claude Agent SDK does not expose subscription usage percentages through its API, so Hive has no way to read the data needed to enforce the thresholds. Scheduled tasks will always run regardless of these values.

A warning is emitted to the worker log at startup whenever a schedule entry has thresholds configured, so you can see the fields are present but inactive.

The fields are kept in the schema for forward compatibility — they will be wired up once the SDK exposes usage data.

| Field | Type | Default | Description |
|---|---|---|---|
| `skip_if_five_hour_above` | float | _(none)_ | _(no-op)_ Intended to skip if 5-hour usage % ≥ this value |
| `skip_if_seven_day_above` | float | _(none)_ | _(no-op)_ Intended to skip if 7-day usage % ≥ this value |
| `notify_on_skip` | bool | `true` | _(no-op)_ Intended to send a Telegram message when the job is skipped |

## Combining both types

A Worker can have any number of `[[schedule]]` entries mixing both types:

```toml
[[schedule]]
cron = "0 7 * * *"
run = "commands/fetch_data.py"

[[schedule]]
cron = "30 7 * * *"
agent_prompt = "Review the data fetched this morning and write a brief summary to memory/daily.md"

[[schedule]]
cron = "0 18 * * 5"
agent_prompt = "It's end of week. Archive completed tasks and reset the task list in memory/tasks.md"

[[schedule]]
cron = "0 0 * * *"
run = "commands/cleanup.py"
```

## Important: no self-restart during scheduled jobs

Scheduled jobs do **not** trigger config change detection or cause the Worker to restart. This is intentional: restarting a Worker mid-schedule (e.g., while an `agent_prompt` job is running) could result in missed jobs, partial writes, or orphaned agent sessions. If you update `hive.toml` while the Worker is running, use `hive restart <path>` manually to apply the new schedule.
