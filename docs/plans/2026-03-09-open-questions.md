# Hive — Open Questions

_Last updated: 2026-03-09_
_Status: All questions resolved._

---

## Q1. Claude Agent SDK — in-process MCP server API ✅ RESOLVED

**Answer:** The SDK supports in-process MCP servers natively. The API is:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeSDKClient, ClaudeAgentOptions

@tool("summarise", "Summarise recent activity from the log", {"n": int})
async def summarise(args):
    n = args["n"]
    # ... invoke script subprocess ...
    return {"content": [{"type": "text", "text": stdout}]}

server = create_sdk_mcp_server(name="commands", version="1.0.0", tools=[summarise, ...])

options = ClaudeAgentOptions(mcp_servers={"commands": server})
async with ClaudeSDKClient(options=options) as client:
    ...
```

**Key constraints:**
- `ClaudeSDKClient` (not `query()`) is required when using SDK MCP server objects.
- `mcp_servers` accepts both in-process SDK server objects and external subprocess dicts (e.g. `{"command": "npx", "args": [...]}`).
- Tools are registered at server-creation time, so `build_mcp_server()` must be called after `discover()` completes.

**Impact on design:**
- `CommandRegistry.build_mcp_server()` should use `@tool` + `create_sdk_mcp_server`. Each `CommandMeta` becomes one `@tool` definition, with its `execute()` method as the handler.
- `WorkerRuntime` must use `ClaudeSDKClient` (async context manager), not the `query()` helper.
- The `ClaudeAgentRunner` class should hold and manage the `ClaudeSDKClient` context.

---

## Q2. Comb server — process wiring and ownership ✅ RESOLVED

**Answer:** Comb is a global Hive service, started once on first `hive init` alongside the LaunchAgent, and always running thereafter.

**Design decisions:**

- `write_comb_block()` is called by `hive init` on first use — the same path that installs the LaunchAgent. Both happen exactly once per machine.
- Comb is registered as `[program:hive-comb]` in `conf.d/hive-comb.conf`, managed by supervisord like any Worker. `autorestart=true` keeps it running.
- The supervisord entrypoint is `hive comb` — an internal CLI command (hidden from help, like `hive run`). Calling `uvicorn` on the FastAPI app directly.
- No `hive comb start/stop` commands needed. Once installed, Comb is always running when supervisord is running. Users never interact with it directly.
- The Comb server reads `HiveRegistry` at startup to discover all Workers and their configs. No per-Worker startup interaction required.

**supervisord block:**
```ini
[program:hive-comb]
command=hive comb
autostart=true
autorestart=true
stdout_logfile=%(ENV_HOME)s/.config/hive/logs/comb.log
stderr_logfile=%(ENV_HOME)s/.config/hive/logs/comb-err.log
```

---

## Q3. `hive init` vs `hive start` — overlap and idempotency contract ✅ RESOLVED

**Answer:** Both commands write the supervisord block. They serve different purposes and both are fully idempotent.

**State machine:**

| State | Definition |
|---|---|
| `unknown` | No folder at the given path |
| `scaffolded` | Folder exists with `hive.toml` + `.env` (may be cloned from git, not necessarily `init`-ed) |
| `registered` | Scaffolded + HiveRegistry entry + supervisord block present |
| `running` | Registered + supervisorctl reports RUNNING |

**Command transitions:**

| Command | Transition | Notes |
|---|---|---|
| `hive init <name>` | `unknown → running` | Scaffolds folder, writes block, registers, reloads supervisord. `autostart=true` + `supervisorctl update` starts the Worker automatically. |
| `hive start <path>` | `scaffolded → running`, `registered → running`, `running → running` | Writes block (idempotent), registers (idempotent), reloads, then explicitly `supervisorctl start`. Safe on never-init'd folders (e.g. cloned from git) provided `hive.toml` + `.env` are present. If already running, reports "Worker is already running." gracefully. |
| `hive stop <path>` | `running → registered` | Stops process; supervisord block and registry entry remain. |
| `hive restart <path>` | `running → running` | `supervisorctl restart`. |

**Idempotency:**
- `hive init` on an already-init'd folder: skips existing scaffolding files, re-registers (idempotent), re-writes supervisord block (idempotent). No error.
- `hive start` on an already-running Worker: writes block (idempotent), registers (idempotent), reloads, then `supervisorctl start` — supervisord returns non-zero; Hive catches this and reports "Worker is already running." without error exit.
- `hive start` on a cloned folder: valid use case — `load_worker_config()` validates `hive.toml` + `.env` present; proceeds normally.

**Sequence summary:**

`hive init`:
```
1. [first use only] ensure_supervisord_conf(), write_comb_block(), install_launchagent(), reload_supervisord()
2. Scaffold folder (git init, .venv, hive.toml + .env templates) — skip if files already exist
3. write_worker_block(name, path)
4. HiveRegistry.register(name, path)
5. reload_supervisord()  ← autostart=true causes Worker to start automatically
```

`hive start`:
```
1. load_worker_config(path)  ← validates hive.toml + .env present
2. write_worker_block(name, path)  ← idempotent
3. HiveRegistry.register(name, path)  ← idempotent
4. reload_supervisord()
5. supervisorctl start <worker_name>
```

**Impact on design:**
- `start()` in `cli/app.py` must call `load_worker_config()` to resolve the worker name (needed for the supervisorctl call), then write block + register + reload + start.
- `init()` must NOT issue `supervisorctl start` explicitly — `supervisorctl update` starts it via `autostart=true`.
- Both use `write_worker_block()` from `shared/supervisor.py`, which is idempotent.

---

## Q4. Agent session resumption — is `session_id` actually supported? ✅ RESOLVED

**Answer:** Session resumption works and persists across process restarts. Sessions are stored locally on disk by the Claude CLI (not server-side).

**Correct API (design doc had wrong parameter name):**

```python
# ❌ Wrong (from the current design doc):
options = ClaudeAgentOptions(..., session_id=session.session_id)

# ✅ Correct:
options = ClaudeAgentOptions(resume=session_id)

# Session ID is captured from the init message:
async for message in query(...):
    if isinstance(message, SystemMessage) and message.subtype == "init":
        session_id = message.session_id  # save this to memory/.sessions.json
```

**Key findings:**
- Sessions are saved to disk by the CLI. `list_sessions()` and `get_session_messages(session_id)` can retrieve them from any subsequent process.
- `resume=session_id` loads the full message history and continues the conversation — works after process restart.
- No TTL documented — sessions appear to persist indefinitely.
- There is also a `fork_session=True` option on `ClaudeAgentOptions` which forks rather than continues a session (not needed for Hive's use case).
- Within a single process, `ClaudeSDKClient` maintains conversation context across multiple `client.query()` calls without needing `resume=` — so `resume=` is only needed at cold start (first message after a Worker restart).

**Impact on design:**
- The `AgentSession` / `memory/.sessions.json` approach is correct and should be kept.
- The design doc's `ClaudeAgentOptions(..., session_id=session.session_id)` must be corrected to `resume=session.session_id`.
- `ClaudeAgentRunner` should use `ClaudeSDKClient` as a long-lived context manager within a single process (one per Worker), passing `resume=` only at instantiation if a prior session ID exists for the given chat ID. Subsequent messages in the same process reuse the same client — no `resume=` needed per-message.

---

## Q5. Worker `.venv` — base requirements ✅ RESOLVED

**Answer:** The worker `.venv` is created bare — no packages pre-installed beyond what the standard venv tooling provides (pip, setuptools, wheel). Python's stdlib is sufficient for most simple scripts.

**Rationale:**
- There is no universal package that every Worker script needs. A budget tracker, a news fetcher, and a calendar bot all need different deps.
- Pre-installing opinionated packages risks version conflicts with user-chosen deps.
- "One folder = one world" means each Worker fully controls its own dependencies.
- Hive already loads `.env` and injects `WORKER_DIR` into script subprocesses, so scripts don't need `python-dotenv` or similar to bootstrap themselves.

**Pattern for adding dependencies:**

`hive init` generates an empty `requirements.txt` in the worker folder with a comment explaining the pattern:

```
# Worker script dependencies
# Install with: .venv/bin/pip install -r requirements.txt
# Example:
# requests>=2.31
# arrow>=1.3
```

Users install into the worker venv with:
```bash
cd my-worker
.venv/bin/pip install -r requirements.txt
```

Or equivalently with uv:
```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

**`hive init` venv creation sequence:**
```
python -m venv .venv           # create bare venv
# No pip install step          # intentionally empty
```

(Hive itself uses `uv` for its own deps; the worker venv is a plain stdlib venv, no uv required for Worker developers.)

---

## Q6. Worker removal — `hive remove` / deregister flow ✅ RESOLVED

**Answer:** `hive remove <path>` is in MVP scope. A framework that can add but not remove Workers is incomplete for real use — without it, users must manually stop the process, delete the conf file, edit `workers.json`, and reload supervisord.

**What removal does (default):**
1. `supervisorctl stop <worker_name>` — stops the process if running (tolerates "not running")
2. `remove_worker_block(worker_name)` — deletes `conf.d/<name>.conf`
3. `HiveRegistry.unregister(name)` — removes entry from `workers.json`
4. `reload_supervisord()` — `supervisorctl update` removes the program from supervisord's view

The Worker **folder is NOT deleted** by default. It is pure data (config, memory, logs) and may contain valuable state. The user deletes it manually if desired.

**`--delete` flag:** Adds a step after step 4: `shutil.rmtree(worker_dir)`. Requires explicit user confirmation (prompt) since this is irreversible. Confirmation prompt: `"Delete folder at <path>? This cannot be undone. [y/N]"`.

**Idempotency / error handling:**
- If the Worker is not running: `supervisorctl stop` returns non-zero; Hive treats this as a no-op (already stopped).
- If no supervisord block exists: `remove_worker_block()` is a no-op.
- If not in HiveRegistry: `unregister()` is a no-op.
- If the folder doesn't exist and `--delete` is passed: no-op (nothing to delete).

**State machine update:**

| Command | Transition |
|---|---|
| `hive remove <path>` | `running/registered → scaffolded` (folder remains) |
| `hive remove <path> --delete` | `running/registered → unknown` (folder deleted) |

**CLI signature:**
```python
@app.command()
def remove(
    path: Path = typer.Argument(...),
    delete: bool = typer.Option(False, "--delete", help="Also delete the worker folder (irreversible)"),
) -> None:
    """Stop and unregister a Worker. The folder is kept unless --delete is passed."""
```

**Impact on design:**
- `remove_worker_block()` in `shared/supervisor.py` is already specced as `def remove_worker_block(worker_name: str) -> None` — no change needed.
- `HiveRegistry.unregister()` is already present in the registry spec.
- Add `remove` command to `cli/app.py` CLI table.
- Add `hive remove` to the Hive CLI reference table in `hive-architecture-design.md`.

---

## Q7. Built-in Hive commands — scope and extensibility ✅ RESOLVED

**Answer:** All design questions are settled. The MVP built-in set is `/reset` and `/help` only.

**Full initial set (MVP):**

| Command | What it does |
|---|---|
| `/reset` | Clears the agent session for the current Telegram chat ID. The next message starts a fresh conversation with no prior context. |
| `/help` | Lists all available commands: built-ins first, then user-defined commands with descriptions. |

**`/status` is deferred post-MVP.** It would show runtime introspection (active sessions, commands loaded, next scheduled run) — useful for debugging but not essential for normal use. The extension point makes adding it trivially easy later.

**Where built-in handlers live:** `src/hive/worker/builtins.py` — a dedicated module, separate from `CommandRegistry`. Contains:
- `BUILTIN_NAMES: set[str] = {"reset", "help"}` — the canonical registry of built-in names; extend this set to add future built-ins.
- `make_reset_handler(agent_runner)` — factory returning the `/reset` handler bound to the given `AgentRunner`.
- `make_help_handler(registry, builtin_names)` — factory returning the `/help` handler.

**Registration:** `WorkerRuntime._register_handlers()` registers built-ins first (before user commands), giving them priority. Subsequent user-defined `CommandHandler`s and the catch-all NL handler are registered after.

**Collision handling:** If a user creates `commands/reset.py` (or any script whose name matches a `BUILTIN_NAMES` entry), Hive logs a warning at startup and the built-in takes precedence. The user script is silently skipped for Telegram registration (but remains available as an agent tool if desired — though this edge case is unlikely given the reserved names).

**Built-ins are never agent tools:** Built-in commands control the runtime, not the Worker's domain logic. They are not registered with the MCP server and are not visible to the agent.

**Extension point:** Adding a new built-in requires three steps:
1. Add the name to `BUILTIN_NAMES` in `worker/builtins.py`.
2. Write a `make_<name>_handler(...)` factory function in `builtins.py`.
3. Wire the factory in `WorkerRuntime._register_handlers()`.

No other files need to change. The collision-detection loop in `_register_handlers()` checks against `BUILTIN_NAMES` automatically.

**Implementation:** Already fully specced in `2026-03-09-hive-code-architecture.md` — Section 3b (`worker/builtins.py`) and Section 6 (`WorkerRuntime._register_handlers()`). No further architectural changes needed.
