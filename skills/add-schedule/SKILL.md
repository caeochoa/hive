---
name: add-schedule
description: "Add a scheduled task to an existing Hive Worker. Walks through job type (run a script vs. send an agent prompt), cron syntax, and optional cost-guard fields. Use when: add schedule, new schedule, add cron, schedule a task, run daily, run weekly, morning brief, scheduled reminder, automate, recurring task."
---

# Add a Schedule to a Hive Worker

You are adding a scheduled task to an existing Hive Worker. Schedules run inside the Worker process on APScheduler — no separate processes or cron daemon needed.

Your job is to understand what the user wants to automate, then add the right `[[schedule]]` block to `hive.toml`.

## How schedules work (essential context)

Each `[[schedule]]` block requires a `cron` field and exactly one of `run` or `agent_prompt`:

```toml
[[schedule]]
cron = "0 8 * * *"             # standard 5-field cron: min hour dom month dow
run = "commands/script.py"     # execute this script (no arguments)

[[schedule]]
cron = "0 9 * * 1"
agent_prompt = "Prepare the weekly summary and write it to memory/weekly.md"
```

**`run` jobs:**
- Execute a command script with no arguments
- Output is logged, not sent to Telegram
- Auto-commits any file changes after completion
- No LLM cost
- Scheduled `run` jobs always invoke the script without arguments — if you need parameterised logic, put it in an `agent_prompt` or hardcode values in a wrapper script

**`agent_prompt` jobs:**
- Route a prompt through the Claude agent
- Response is sent to each allowed user via Telegram
- Incurs LLM cost — consider cost-guard fields
- Auto-commits any file changes after completion

**Cron syntax (5 fields, left to right):**

| Field | Range | Examples |
|---|---|---|
| minute | 0–59 | `0`, `*/15` |
| hour | 0–23 | `8`, `20` |
| day of month | 1–31 | `1`, `15` |
| month | 1–12 | `*`, `6` |
| day of week | 0–6 (Sun=0) | `1` (Mon), `5` (Fri) |

Common examples:
- `0 8 * * *` — every day at 08:00
- `0 9 * * 1` — every Monday at 09:00
- `0 20 * * 1-5` — weekdays at 20:00
- `0 */6 * * *` — every 6 hours

**Cost-guard fields (for `agent_prompt` jobs):**

```toml
[[schedule]]
cron = "0 8 * * *"
agent_prompt = "Send the morning brief"
skip_if_five_hour_above = 0.50   # skip if 5-hour spend exceeds $0.50
skip_if_seven_day_above = 5.00   # skip if 7-day spend exceeds $5.00
notify_on_skip = true            # send Telegram message when skipped (default: true)
```

Usage data is tracked internally by Hive. Scheduled jobs are skipped (not cancelled) — they resume at the next scheduled time if spend drops below the threshold.

**Important:** Scheduled jobs do NOT trigger config reload or Worker restart. After editing `hive.toml`, apply with:

```bash
hive restart ./<worker-name>
```

## Step 1: Read the existing Worker

Before adding a schedule:

1. Read `hive.toml` — existing schedules, agent model, system prompt
2. List `commands/` — what scripts are available for `run` jobs
3. Understand what the Worker already does — so the schedule fits naturally

## Step 2: Clarify the schedule

Ask the user (or infer from context) what they want automated:

- **What should happen?** Describe the task
- **When should it run?** Time, day, frequency
- **Script or agent prompt?** Use `run` if there's a command script that does exactly this with no arguments. Use `agent_prompt` if you want the agent to reason, write summaries, or send a natural language message.
- **For `agent_prompt` jobs:** Does the user want cost-guard thresholds? Suggest reasonable defaults if they're running multiple scheduled prompts.

If the right command script doesn't exist yet for a `run` job, offer to create it (or suggest using the `add-command` skill).

## Step 3: Write the `[[schedule]]` block

Add the block to `hive.toml`. Multiple `[[schedule]]` sections are fine — TOML array-of-tables syntax handles it.

For `agent_prompt` jobs, recommend cost-guard fields if the Worker already has other scheduled prompts or if the cron is frequent (more than daily).

## Step 4: Apply and verify

After updating `hive.toml`:

1. Restart the Worker to pick up the new schedule:
   ```bash
   hive restart ./<worker-name>
   ```
2. Tell the user when the first run will occur based on the cron expression
3. Remind them where to watch for output:
   - `run` jobs: `hive logs ./<worker-name>` or the Comb log cell
   - `agent_prompt` jobs: Telegram message sent to allowed users

## Important guidelines

- **Prefer `run` over `agent_prompt` for deterministic tasks.** If the output is predictable (fetch data, write a file, send a fixed report), use a script — it's cheaper, faster, and more reliable.
- **Use `agent_prompt` for synthesis tasks.** Summarising recent activity, generating a narrative brief, or making a judgment call based on current state are good uses for the agent.
- **Write `agent_prompt` strings that are specific.** "Send the morning brief" is vague. "Read memory/activity.md, summarise the last 24 hours of activity in 3 bullet points, and send it as the morning brief" gives the agent clear instructions.
- **Always suggest cost-guard fields for `agent_prompt` jobs on frequent schedules.** A bug or runaway prompt on an hourly schedule can be expensive.
