# Hive Design Review

_Date: 2026-03-10_
_Status: Resolved — all actionable issues addressed in design documents_

---

## Critical — Must fix before implementation

### 1. Scheduled `agent_prompt` has no chat_id

**Location:** architecture-design.md §2 (scheduler), code-architecture.md §5 (WorkerScheduler)

`AgentRunner.run()` requires `chat_id: int`, but cron-triggered `agent_prompt` jobs have no Telegram message and therefore no chat_id. The scheduler literally cannot call the agent as currently designed.

**Options:**
- A. Use a synthetic chat_id (e.g., `0`) for headless/scheduled sessions.
- B. Add a separate `run_headless(prompt: str) -> str` method to `AgentRunner` that creates a one-shot session with no chat association.
- C. Make `chat_id` optional in `run()` — `None` means headless.

**Related:** Where does the agent's text response go? For user-initiated messages it goes to Telegram. For scheduled prompts, the response is captured but never routed anywhere. Options: log it, write it to a file, or discard it (if the prompt's side-effects via tools are the point).

**Resolution:** Option C adopted. `AgentRunner.run()` signature changed to `chat_id: int | None`. When `chat_id=None`, `ClaudeAgentRunner` creates a one-shot client (no resume, no session storage, discarded after use). `WorkerScheduler` now accepts `bot` and `allowed_user_id` at construction, and sends scheduled prompt responses to the user's Telegram chat via `_send_long_message`. Architecture-design.md §2 updated to note that scheduled responses go to the user's chat.

---

### 2. `asyncio.run()` double-loop in shutdown

**Location:** code-architecture.md §9, `cli/app.py: run()` (lines 670–686)

```python
asyncio.run(runtime.start())   # creates event loop, blocks
# ...
asyncio.run(runtime.stop())    # creates a NEW event loop
```

`runtime.stop()` needs to close async resources (agent clients, Telegram app, scheduler) that were created on the first loop. A second `asyncio.run()` creates a fresh loop — those resources are orphaned and connections leak.

**Fix:** Register a signal handler inside `start()` that calls `stop()` on the same loop, or use `loop.run_until_complete()` with a single loop instance.

**Resolution:** Added `WorkerRuntime.run()` as the top-level entry point. CLI now calls `asyncio.run(runtime.run())` — single event loop. `run()` calls `start()`, installs SIGTERM/SIGINT handlers via `loop.add_signal_handler()`, awaits a shutdown event, and calls `stop()` in a finally block. `start()` uses non-blocking Telegram startup (`app.initialize()` → `app.start()` → `app.updater.start_polling()`) instead of `app.run_polling()`. §12 startup sequence updated to reflect the new flow.

---

### 3. Concurrent message handling — no locking

**Location:** code-architecture.md §6 (WorkerRuntime), §3 (ClaudeAgentRunner)

`python-telegram-bot` can dispatch multiple update handlers concurrently on the same event loop. If two Telegram messages arrive for the same `chat_id` simultaneously, both call `ClaudeAgentRunner.run()` on the same `ClaudeSDKClient` — a race condition.

Additionally, a scheduler job and a user message could both trigger `_auto_commit()` concurrently, causing git conflicts.

**Fix:** Add a per-`chat_id` `asyncio.Lock` in `ClaudeAgentRunner`, and a separate lock around `_auto_commit()`.

**Resolution:** `ClaudeAgentRunner` now has `self._locks: dict[int, asyncio.Lock]` and a `_get_lock(chat_id)` helper. Interactive `run()` calls wrap all chat_id-specific logic with `async with self._get_lock(chat_id)`. One-shot runs (chat_id=None) don't need locking. `WorkerRuntime` has `self._commit_lock = asyncio.Lock()` and `_auto_commit()` is wrapped with `async with self._commit_lock`.

---

## Important — Should fix before or during implementation

### 4. Worker name — no single source of truth

**Location:** SPEC.md §6, code-architecture.md §9 (`cli/app.py: init`)

`hive init <name>` takes the name as a CLI argument and writes it into `hive.toml` as `worker.name`. Later, `hive start <path>` reads the name from `hive.toml`. If the user edits `hive.toml` to change the name, the supervisord block (keyed by the original name) and the registry entry diverge silently.

**Options:**
- A. The name in `hive.toml` is always authoritative. `hive start` detects stale supervisord blocks/registry entries by comparing, and updates them.
- B. Document that renaming requires `hive remove` + `hive start` (explicit re-registration).

**Resolution:** Option A adopted. `hive start` now includes a name reconciliation step: if `hive.toml` name differs from the existing supervisord block or registry entry for that path, the stale block/entry is removed before proceeding with the current name. `hive.toml` is always authoritative.

---

### 5. Telegram 4096-character message limit

**Location:** code-architecture.md §6 (`_handle_nl_message`), §4 (`CommandRegistry.telegram_handlers`)

Agent responses and command stdout can easily exceed Telegram's 4096-character limit. `update.message.reply_text()` will raise `BadRequest`.

**Fix:** Add a helper that splits long text into chunks at line boundaries and sends multiple messages.

**Resolution:** Added `WorkerRuntime._send_long_message(target, text)` static method that splits text into ≤4096-char chunks at line boundaries. Used in `_handle_nl_message`, command handler callbacks, and by `WorkerScheduler` for scheduled prompt responses.

---

### 6. Comb doesn't discover new Workers after startup

**Location:** code-architecture.md §10 (`comb/server.py` lifespan)

The Comb server loads `HiveRegistry` at startup and caches all worker configs. Workers added via `hive init` after Comb starts won't appear in the dashboard until Comb is restarted.

**Options:**
- A. Re-read the registry on each request to `/` (list view). Worker configs can be cached with a short TTL.
- B. `hive init` and `hive remove` call `supervisorctl restart hive-comb` after modifying the registry.
- C. Accept the limitation for MVP and document it.

**Resolution:** Option A adopted. Replaced the startup-time `lifespan` loading with an on-demand `_load_workers()` function that re-reads the registry with a 5-second TTL cache (`time.monotonic()`). New Workers appear on the next dashboard request without restarting Comb.

---

### 7. `__aexit__` called directly on ClaudeSDKClient

**Location:** code-architecture.md §3 (`ClaudeAgentRunner.reset_session`, `close`)

```python
await self._clients.pop(chat_id).__aexit__(None, None, None)
```

Calling dunder context manager methods directly is fragile. If the client's `__aexit__` relies on being called from an `async with` block or expects exception info, this could silently fail or leak resources.

**Fix:** Store clients alongside an `asyncio.Task` or use a wrapper that properly manages the context. Alternatively, if the SDK exposes a `.close()` method, use that instead.

**Resolution:** Added `self._exit_stacks: dict[int, contextlib.AsyncExitStack]`. `_get_or_create_client` uses `AsyncExitStack.enter_async_context(client)` instead of `client.__aenter__()`. `reset_session` calls `await self._exit_stacks.pop(chat_id).aclose()`. `close` iterates stacks calling `await stack.aclose()`.

---

### 8. `git add -A` in auto-commit is too broad

**Location:** code-architecture.md §6 (`_auto_commit`)

`git add -A` stages everything not in `.gitignore`. Scripts may create temporary files, core dumps, or large binary artifacts that shouldn't be committed. The default `.gitignore` template only covers `.env`, `.venv/`, and `logs/`.

**Options:**
- A. Use `git add commands/ memory/ hive.toml dashboard/` — explicitly stage only known directories.
- B. Ship a more comprehensive default `.gitignore` (e.g., `*.pyc`, `__pycache__/`, `*.tmp`, `.DS_Store`).
- C. Both.

**Resolution:** Option C adopted. `_auto_commit` now uses `git add commands/ memory/ hive.toml dashboard/` instead of `git add -A`. The `.gitignore` template in `hive init` step 11 expanded to include `*.pyc`, `__pycache__/`, `*.tmp`, `.DS_Store` in addition to `.env`, `.venv/`, `logs/`.

---

## Minor — Fix opportunistically

### 9. `datetime.utcnow()` is deprecated

**Location:** code-architecture.md §2 (`AgentSession` dataclass)

`datetime.utcnow()` is deprecated since Python 3.12 (the target runtime). Use `datetime.now(datetime.UTC)`.

**Resolution:** All three occurrences replaced: `AgentSession.created_at` and `last_active` default factories, and the `last_active` update in `ClaudeAgentRunner.run()`.

---

### 10. Open questions doc numbering is out of order

**Location:** 2026-03-09-open-questions.md

Q6 appears after Q7.

**Resolution:** Swapped Q6 and Q7 sections so they appear in numerical order (Q6: Worker removal, Q7: Built-in commands).

---

### 11. State machine in Q3 is incomplete

**Location:** 2026-03-09-open-questions.md §Q3

The command transitions table shows `hive start` as `scaffolded → running`, but it also handles `registered → running` and `running → running` (already running). The table should show all valid transitions.

**Resolution:** Expanded `hive start` row to show all three valid transitions: `scaffolded → running`, `registered → running`, `running → running` (already running).

---

## Long-term limitations (not blockers, but worth documenting)

### 12. macOS-only process management

LaunchAgents are macOS-specific. There's no abstraction layer for Linux (systemd user units) or Windows. Worth stating this explicitly as a design boundary in SPEC.md if that's the intent, or noting it as a future extension point.

### 13. No agent cost or rate controls

With `Bash` in allowed tools and `max_turns=10`, a single message can trigger 10 Claude API calls with arbitrary shell commands. Scheduled `agent_prompt` jobs compound this. There's no per-day budget, cost tracking, or circuit breaker. Acceptable for personal use, but a misconfigured cron could burn through significant API usage.

### 14. No config hot-reload

Changes to `hive.toml` (new commands, schedule changes, cell layout) require `hive restart`. No file-watching. Fine for MVP but worth documenting for users.

### 15. Single-user auth model

`TELEGRAM_ALLOWED_USER_ID` is a single integer. No path to multi-user (e.g., a shared household bot) without reworking the auth guard. Fine for the "personal tool" scope — just a known boundary.

### 16. No session eviction

`ClaudeAgentRunner` accumulates one `ClaudeSDKClient` per `chat_id` in memory, and sessions accumulate indefinitely in `memory/.sessions.json`. No TTL or eviction policy. For a personal bot with one user this is fine, but the data structure grows without bound.
