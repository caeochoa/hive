# Agent

The agent is the natural language interface for each Worker. Every non-command message sent to the Telegram bot is routed to the Claude Agent SDK. This document covers configuration, tools, session management, self-configuration, and logging.

---

## 1. Agent Configuration (`hive.toml`)

All agent settings live under the `[agent]` section.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | string | `"claude-haiku-4-5"` | Claude model ID to use |
| `memory_dir` | string | `"memory/"` | Directory for agent memory and session state; relative to worker dir |
| `max_turns` | int | `10` | Maximum agent turns per incoming message |
| `system_prompt` | string | _(none)_ | Custom system prompt. If set, self-config instructions are NOT appended (see §6) |
| `thinking_budget_tokens` | int | _(none)_ | Enable extended thinking with this token budget (see §5) |

```toml
[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
# system_prompt = "You are a budget tracker assistant."
# thinking_budget_tokens = 5000
```

---

## 2. Built-in Agent Tools

The agent always has access to the following tools:

**Filesystem tools** (always available):
- `Read` — read files
- `Write` — write files
- `Bash` — run shell commands
- `Glob` — file pattern matching

**Command tools** — all scripts in `commands/` are auto-discovered at startup and exposed as MCP tools. The same scripts that register as Telegram slash commands are available to the agent.

**Built-in MCP tool** — `set_session_config` is always available when there is an active Telegram chat session. The agent uses it to adjust its own runtime behavior (see §4).

---

## 3. Session Persistence

Each Telegram chat ID maps to a persistent agent session. Sessions are stored in `memory/.sessions.json` and survive worker restarts.

- A new session is created on first contact from a chat ID.
- On restart, the session ID is loaded from disk and the conversation context is resumed.
- `/reset` closes the client, deletes the session record, and clears all overrides for that chat. The next message starts a completely fresh session.

The sessions file is auto-committed to the worker git repo after each agent turn.

---

## 4. Session Overrides

Session overrides change agent config for a single chat without touching `hive.toml`. Overrides are in-memory only and are cleared by `/reset` or a worker restart.

Overrides take effect from the **next message** after they are set — the current turn completes with the old settings.

### Via `/set` Telegram command

```
/set model claude-opus-4-6
/set max_turns 20
/set thinking_budget_tokens 5000
/set reset
```

Rules:
- `model` value must start with `claude-`
- `max_turns` and `thinking_budget_tokens` must be integers
- `/set` with no arguments prints usage

To revert all overrides to `hive.toml` defaults: **`/set reset`**


### Via `set_session_config` MCP tool (agent-initiated)

The agent may call this tool during a conversation to adjust its own behavior. Parameters are all optional:

| Parameter | Type | Description |
|---|---|---|
| `model` | string | Claude model ID for this session |
| `max_turns` | int | Max turns per message for this session |
| `thinking_budget_tokens` | int | Extended thinking budget; set to `0` to disable |

Changes take effect from the next message. Overrides reset on `/reset` or worker restart.

---

## 5. Extended Thinking

Extended thinking allocates additional compute for harder reasoning tasks. It produces higher quality responses at higher cost and slower speed.

**Permanent (via `hive.toml`):**
```toml
[agent]
thinking_budget_tokens = 5000
```

**Per-session (via Telegram):**
```
/set thinking_budget_tokens 5000
```

**Per-session (agent-initiated):**

The agent calls `set_session_config` with `thinking_budget_tokens = 5000`.

Set `thinking_budget_tokens = 0` in a session override to disable thinking for a session where it was enabled by `hive.toml`.

---

## 6. Worker Self-Configuration

By default (no custom `system_prompt`), the agent's system prompt includes instructions that allow it to reconfigure the worker:

- Edit `hive.toml` to change model, add/remove schedules, update comb cells, etc.
- Create or edit files in `commands/` to add or modify agent tools and Telegram commands.

After each interactive turn (a message from a Telegram user), the runtime checks whether `hive.toml` or any `commands/*.py` file changed. If changes are detected:

1. The bot sends a notification: `"Config updated. Restarting worker to apply changes..."`
2. After a 1.5-second delay, the process sends `SIGTERM` to itself.
3. supervisord catches the signal and restarts the process with the new configuration.
4. Sessions are preserved via `memory/.sessions.json`, so the conversation continues seamlessly after restart.

**Important constraints:**

- Change detection only runs after interactive turns. Scheduled `agent_prompt` tasks do not trigger restarts. This prevents unattended restarts mid-schedule — the restart will happen on the next interactive turn instead.
- If delivering the Telegram reply fails (e.g. network error), the restart is skipped for that turn. This is intentional: if the response couldn't be delivered, it's unclear whether the agent turn completed cleanly.
- If you set a custom `system_prompt` in `hive.toml`, the self-config instructions are not added to the prompt. The agent will not know it can edit `hive.toml` or `commands/` unless you include those instructions yourself.

---

## 7. Memory Patterns

`memory/` is the agent's primary read/write state store. All files in `memory/` (and `commands/`, `hive.toml`, `dashboard/`) are auto-committed to the worker's git repo after each agent turn.

Common patterns:

| Pattern | Example |
|---|---|
| Persist notes | Write summaries or context to `memory/notes.md` |
| Track state | Store counters and flags in `memory/stats.json` |
| Weekly reports | Write formatted reports to `memory/weekly.md` |
| Conversation context | Use `memory/context.md` to carry information across sessions |

Avoid writing large ephemeral data to `memory/` — the agent will read it back on subsequent turns, consuming context window. Keep memory files concise and structured.

The sessions file (`memory/.sessions.json`) is managed by Hive and should not be edited manually.

---

## 8. Logging

All SDK activity is logged to the worker log stream. View logs with:

```bash
hive logs <path>
hive logs <path> -f    # follow
```

Log line tags and what they mean:

| Tag | Level | Description |
|---|---|---|
| `[tool_use]` | INFO | Tool called by the agent; shows tool name and truncated input |
| `[tool_result]` | INFO | Tool result received; shows character count |
| `[tool_error]` | ERROR | Tool call failed; shows truncated error preview |
| `[thinking]` | INFO | Extended thinking block; shows character count |
| `[result]` | INFO | Turn summary: turn count, total cost, and stop reason |

Full tool inputs and outputs are logged at DEBUG level. The `[result]` line is emitted at the end of every agent turn and is the quickest way to see cost and stop reason at a glance.

Example log output:
```
2025-03-27 10:00:01 hive.worker.agent INFO [tool_use] Read input={'file_path': 'memory/notes.md'}
2025-03-27 10:00:02 hive.worker.agent INFO [tool_result] a1b2c3d4 → 412 chars
2025-03-27 10:00:03 hive.worker.agent INFO [result] turns=2 cost=$0.0012 stop=end_turn
```
