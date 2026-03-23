# Hive — Code Architecture

_Last updated: 2026-03-09_
_Status: Pre-implementation design — authoritative reference for all implementation work_

---

## 1. Module Structure

```
src/hive/
├── __init__.py          # entry point: main() → Typer app
├── cli/
│   └── app.py           # all CLI commands (Typer)
├── worker/
│   ├── runtime.py       # WorkerRuntime: event loop, auth, message routing
│   ├── commands.py      # CommandRegistry: discovery, subprocess exec, MCP server
│   ├── builtins.py      # Built-in Hive commands (/reset, /help, …)
│   ├── agent.py         # AgentRunner ABC + ClaudeAgentRunner implementation
│   └── scheduler.py     # WorkerScheduler (APScheduler 3.x AsyncIOScheduler)
├── comb/
│   ├── server.py        # FastAPI dashboard server, SSE log streaming
│   └── cells.py         # Cell rendering: render_file_cell, render_metric_cell, tail_log_file
└── shared/
    ├── models.py        # Shared data types (CommandMeta, CombCell, AgentSession, …)
    ├── config.py        # WorkerConfig + load_worker_config()
    ├── registry.py      # HiveRegistry: read/write ~/.config/hive/workers.json
    └── supervisor.py    # supervisord config management + supervisorctl wrappers
```

`src/hive/__init__.py`:
```python
from hive.cli.app import app

def main() -> None:
    app()
```

---

## 2. Data Models

### 2.1 shared/models.py — Shared types

```python
from pydantic import BaseModel, Field, model_validator
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

class CommandArg(BaseModel):
    name: str
    type: str                   # "str" | "int" | "float" | "bool"
    description: str
    default: str | int | float | bool | None = None
    required: bool = True

class CommandMeta(BaseModel):
    name: str                   # matches script filename stem
    description: str
    args: list[CommandArg] = Field(default_factory=list)
    script_path: Path           # absolute path to .py file

class ScheduleEntry(BaseModel):
    cron: str                   # standard 5-field cron expression
    run: str | None = None      # relative path, e.g. "commands/morning_brief.py"
    agent_prompt: str | None = None

    @model_validator(mode="after")
    def exactly_one_action(self) -> "ScheduleEntry":
        if bool(self.run) == bool(self.agent_prompt):
            raise ValueError("Each schedule entry needs exactly one of 'run' or 'agent_prompt'")
        return self

class CombCell(BaseModel):
    type: Literal["log", "file", "metric"]
    title: str
    source: str                 # relative path from worker root
    key: str | None = None      # required when type == "metric"

    @model_validator(mode="after")
    def metric_requires_key(self) -> "CombCell":
        if self.type == "metric" and not self.key:
            raise ValueError("'metric' cells require a 'key' field")
        return self

@dataclass
class AgentSession:
    chat_id: int
    session_id: str             # opaque ID for Claude Agent SDK
    created_at: datetime = field(default_factory=lambda: datetime.now(datetime.UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(datetime.UTC))

@dataclass
class WorkerEntry:
    name: str
    path: Path                  # absolute path to worker folder
```

### 2.2 shared/config.py — WorkerConfig

```python
import tomllib, os
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from hive.shared.models import ScheduleEntry, CombCell

class WorkerSection(BaseModel):
    name: str

class AgentSection(BaseModel):
    model: str = "claude-haiku-4-5"
    memory_dir: str = "memory/"
    max_turns: int = 10
    system_prompt: str = "You are a worker agent. Your world is this folder."

class CombSection(BaseModel):
    cells: list[CombCell] = Field(default_factory=list)

class WorkerConfig(BaseModel):
    worker: WorkerSection
    agent: AgentSection = Field(default_factory=AgentSection)
    schedule: list[ScheduleEntry] = Field(default_factory=list)
    comb: CombSection = Field(default_factory=CombSection)

    # Injected by loader — not from TOML, excluded from serialisation
    worker_dir: Path = Field(exclude=True)
    bot_token: str = Field(exclude=True)
    allowed_user_id: int = Field(exclude=True)

    @property
    def memory_path(self) -> Path:
        return self.worker_dir / self.agent.memory_dir

    @property
    def commands_path(self) -> Path:
        return self.worker_dir / "commands"

    @property
    def logs_path(self) -> Path:
        return self.worker_dir / "logs"

    @property
    def venv_python(self) -> Path:
        return self.worker_dir / ".venv" / "bin" / "python"

class ConfigError(Exception):
    """Raised when config loading fails with a human-readable message."""

def load_worker_config(worker_dir: Path) -> WorkerConfig:
    """
    Load and validate WorkerConfig for the given worker directory.
    1. Resolve path, assert directory exists.
    2. Load .env via python-dotenv.
    3. Parse hive.toml via tomllib (stdlib, Python 3.11+).
    4. Validate with Pydantic into WorkerConfig.
    5. Pull and validate secrets from env vars.
    6. Inject worker_dir, bot_token, allowed_user_id.
    Raises ConfigError with human-readable message on any failure.
    """
    ...
```

---

## 3. Agent Abstraction — ABC

```python
# src/hive/worker/agent.py
from abc import ABC, abstractmethod
from pathlib import Path

class AgentRunner(ABC):
    """
    Abstract interface for the agent subsystem.
    Implement this to swap the Claude Agent SDK for another LLM backend.
    """

    @abstractmethod
    async def run(self, message: str, chat_id: int | None, worker_dir: Path) -> str:
        """
        Send a natural language message to the agent for the given chat_id.
        Returns the full text response. Manages sessions internally.

        chat_id=None means a one-shot scheduled run: fresh client, no session
        persistence, client discarded after use.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release held resources (MCP connections, save sessions)."""
        ...


class ClaudeAgentRunner(AgentRunner):
    """Concrete implementation backed by the Claude Agent SDK.

    Holds one ClaudeSDKClient per chat_id as a long-lived async context manager.
    ClaudeSDKClient is required (not query()) because commands_mcp is an in-process
    SDK MCP server object created by create_sdk_mcp_server().

    One-shot sessions (chat_id=None) are used for scheduled agent_prompt jobs:
    fresh client, no resume, no session storage, discarded after use.
    """

    def __init__(
        self,
        config: AgentSection,
        commands_mcp,               # in-process SDK MCP server from CommandRegistry
        sessions_file: Path,
        worker_dir: Path,
    ) -> None:
        self._config = config
        self._commands_mcp = commands_mcp
        self._worker_dir = worker_dir
        self._sessions: dict[int, AgentSession] = {}
        self._sessions_file = sessions_file
        self._clients: dict[int, "ClaudeSDKClient"] = {}  # one per chat_id
        self._exit_stacks: dict[int, "contextlib.AsyncExitStack"] = {}
        self._locks: dict[int, asyncio.Lock] = {}  # per-chat_id concurrency guard
        self._load_sessions()

    def _load_sessions(self) -> None: ...     # deserialise memory/.sessions.json
    def _save_sessions(self) -> None: ...     # serialise to memory/.sessions.json
    def _get_or_create_session(self, chat_id: int) -> AgentSession: ...

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        """Return the per-chat_id lock, creating on first use."""
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    async def reset_session(self, chat_id: int) -> None:
        """Clear session for chat_id and close its client, forcing a fresh conversation."""
        if chat_id in self._exit_stacks:
            await self._exit_stacks.pop(chat_id).aclose()
            self._clients.pop(chat_id, None)
        self._sessions.pop(chat_id, None)
        self._save_sessions()

    async def _get_or_create_client(self, chat_id: int) -> "ClaudeSDKClient":
        """
        Return the long-lived ClaudeSDKClient for this chat_id, creating it on first use.
        Passes resume=session_id at creation if a prior session exists (cold start).
        Subsequent messages in the same process reuse the same client — no resume= needed.
        """
        if chat_id not in self._clients:
            import contextlib
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, SystemMessage
            session = self._get_or_create_session(chat_id)
            options = ClaudeAgentOptions(
                system_prompt=self._config.system_prompt,
                allowed_tools=["Read", "Write", "Bash", "Glob"],
                permission_mode="acceptEdits",
                cwd=str(self._worker_dir),
                mcp_servers={"commands": self._commands_mcp},
                model=self._config.model,
                max_turns=self._config.max_turns,
                resume=session.session_id or None,  # None = new session
            )
            client = ClaudeSDKClient(options=options)
            stack = contextlib.AsyncExitStack()
            await stack.enter_async_context(client)
            self._clients[chat_id] = client
            self._exit_stacks[chat_id] = stack
        return self._clients[chat_id]

    async def _create_one_shot_client(self) -> tuple["ClaudeSDKClient", "contextlib.AsyncExitStack"]:
        """
        Create a disposable client for scheduled agent_prompt jobs.
        No resume, no session storage. Caller must close the stack when done.
        """
        import contextlib
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        options = ClaudeAgentOptions(
            system_prompt=self._config.system_prompt,
            allowed_tools=["Read", "Write", "Bash", "Glob"],
            permission_mode="acceptEdits",
            cwd=str(self._worker_dir),
            mcp_servers={"commands": self._commands_mcp},
            model=self._config.model,
            max_turns=self._config.max_turns,
        )
        client = ClaudeSDKClient(options=options)
        stack = contextlib.AsyncExitStack()
        await stack.enter_async_context(client)
        return client, stack

    async def run(self, message: str, chat_id: int | None, worker_dir: Path) -> str:
        from claude_agent_sdk import AssistantMessage, TextBlock, SystemMessage

        # --- One-shot (scheduled) run: no session, no persistence ---
        if chat_id is None:
            client, stack = await self._create_one_shot_client()
            try:
                await client.query(message)
                chunks: list[str] = []
                async for event in client.receive_response():
                    if isinstance(event, AssistantMessage):
                        for block in event.content:
                            if isinstance(block, TextBlock):
                                chunks.append(block.text)
                return "".join(chunks)
            finally:
                await stack.aclose()

        # --- Interactive (chat_id-bound) run: persistent session ---
        async with self._get_lock(chat_id):
            client = await self._get_or_create_client(chat_id)
            await client.query(message)
            chunks: list[str] = []
            async for event in client.receive_response():
                if isinstance(event, SystemMessage) and event.subtype == "init":
                    session = self._get_or_create_session(chat_id)
                    if not session.session_id:
                        session.session_id = event.session_id
                        self._save_sessions()
                elif isinstance(event, AssistantMessage):
                    for block in event.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
            session = self._sessions.get(chat_id)
            if session:
                session.last_active = datetime.now(datetime.UTC)
                self._save_sessions()
            return "".join(chunks)

    async def close(self) -> None:
        for stack in self._exit_stacks.values():
            await stack.aclose()
        self._clients.clear()
        self._exit_stacks.clear()
        self._save_sessions()
```

To add a new agent backend (e.g. local Ollama), subclass `AgentRunner` and implement `run()` and `close()`.

---

## 3b. worker/builtins.py — Built-in Hive Commands

Built-in commands are registered by `WorkerRuntime` before user-defined commands and are never exposed as agent tools.

```python
# src/hive/worker/builtins.py
from typing import Callable, Awaitable
from telegram import Update
from telegram.ext import ContextTypes

# Each built-in is an async function matching the python-telegram-bot handler signature.
BuiltinHandler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]

BUILTIN_NAMES: set[str] = {"reset", "help"}
# Extend this set when adding new built-ins. WorkerRuntime checks for collisions at startup.


async def make_reset_handler(agent_runner) -> BuiltinHandler:
    """
    Returns a /reset handler bound to the given AgentRunner.
    Clears the session for the sending chat ID and confirms to the user.
    """
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        await agent_runner.reset_session(chat_id)
        await update.message.reply_text("Session reset. Starting fresh.")
    return handle


async def make_help_handler(registry, builtin_names: set[str]) -> BuiltinHandler:
    """
    Returns a /help handler that lists all available commands.
    Shows built-in commands first, then user-defined commands with their descriptions.
    """
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        lines = ["*Built-in commands:*", "/reset — Start a fresh conversation", "/help — Show this message", ""]
        if registry.commands:
            lines.append("*Worker commands:*")
            for meta in registry.commands.values():
                lines.append(f"/{meta.name} — {meta.description}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    return handle
```

`AgentRunner` must expose a `reset_session(chat_id: int)` method that removes the session entry from `memory/.sessions.json`.

---

## 4. CommandRegistry

```python
# src/hive/worker/commands.py

class CommandError(Exception):
    def __init__(self, stderr: str) -> None:
        self.stderr = stderr
        super().__init__(f"Command failed: {stderr}")

class CommandRegistry:
    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._commands: dict[str, CommandMeta] = {}

    def discover(self) -> None:
        """
        Glob commands/*.py. Parse YAML docstring from each file.
        Build CommandMeta. Log and skip scripts with invalid metadata.
        """
        ...

    def _parse_script(self, path: Path) -> CommandMeta:
        """
        Extract leading docstring, parse as YAML.
        Validate required keys: name, description.
        Construct absolute script_path.
        """
        ...

    async def execute(
        self,
        meta: CommandMeta,
        args: dict[str, str | int | float | bool],
    ) -> str:
        """
        Run: .venv/bin/python commands/<script>.py --key value …
        Sets WORKER_DIR env var.
        Returns stdout. Raises CommandError on non-zero exit.
        """
        ...

    def telegram_handlers(self) -> list:
        """
        Return python-telegram-bot CommandHandler for each registered command.
        Each handler extracts args from message text and calls execute().
        """
        ...

    def build_mcp_server(self):
        """
        Build in-process MCP server wrapping each command as a tool.
        Tool schema derived from CommandMeta. Tool calls delegate to execute().
        Returns MCPServerConfig for ClaudeAgentOptions.mcp_servers.
        """
        ...

    @property
    def commands(self) -> dict[str, CommandMeta]:
        return dict(self._commands)
```

A script works identically whether triggered by `/summarise 10` or by the agent calling the `summarise` tool — both paths go through `execute()`.

---

## 5. WorkerScheduler

```python
# src/hive/worker/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # APScheduler 3.x

class WorkerScheduler:
    def __init__(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AgentRunner,
        bot: "telegram.Bot",
        allowed_user_id: int,
        auto_commit: "Callable[[str], Awaitable[None]]",
    ) -> None:
        self._config = config
        self._registry = registry
        self._agent = agent
        self._bot = bot
        self._allowed_user_id = allowed_user_id
        self._auto_commit = auto_commit
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        """
        Register each [[schedule]] block as an APScheduler CronTrigger job.

        - run entry → calls registry.execute() + auto-commit
        - agent_prompt entry:
            1. Call agent.run(prompt, chat_id=None, ...) — one-shot, no session
            2. Send response to user via _send_long_message(bot, allowed_user_id, response)
            3. Trigger auto-commit

        Adds job error listener to log failures without crashing.
        scheduler.start() is non-blocking — hooks into the running event loop.

        Pseudocode for agent_prompt job:
            async def _run_agent_prompt(prompt: str) -> None:
                response = await self._agent.run(prompt, chat_id=None, worker_dir=self._config.worker_dir)
                await _send_long_message(self._bot, self._allowed_user_id, response)
                await self._auto_commit(f"scheduled prompt: {prompt[:50]}")
        """
        ...

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
```

`AsyncIOScheduler.start()` is non-blocking. It attaches to the running event loop. The runtime's `run()` method awaits a shutdown event, allowing the scheduler to fire jobs independently alongside Telegram polling.

---

## 6. WorkerRuntime

```python
# src/hive/worker/runtime.py

class WorkerRuntime:
    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._registry = CommandRegistry(config)
        self._scheduler: WorkerScheduler | None = None
        self._agent: AgentRunner | None = None
        self._app = None  # python-telegram-bot Application
        self._shutdown_event: asyncio.Event | None = None
        self._commit_lock = asyncio.Lock()

    async def run(self) -> None:
        """
        Top-level entry point — called by asyncio.run() from CLI.
        Starts all subsystems, installs signal handlers, waits for shutdown,
        then stops everything on the same event loop.
        """
        await self.start()
        loop = asyncio.get_running_loop()
        self._shutdown_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown_event.set)
        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    async def start(self) -> None:
        """
        Full startup sequence — see section 12.
        Uses non-blocking Telegram startup:
          app.initialize() → app.start() → app.updater.start_polling()
        Does NOT call app.run_polling() (which blocks and owns the loop).
        """
        ...

    async def stop(self) -> None:
        """Graceful shutdown: stop scheduler → close agent → stop Telegram polling → stop app."""
        ...

    def _is_allowed(self, update) -> bool:
        """Auth guard: return True only if update.effective_user.id == allowed_user_id."""
        ...

    def _register_handlers(self) -> None:
        """
        Register all Telegram handlers on self._app.
        Order matters: built-ins are registered first and take precedence.

        1. Register built-in handlers from worker/builtins.py.
           Log a warning for any user command whose name collides with BUILTIN_NAMES.
        2. Register user-defined command handlers from self._registry.telegram_handlers().
        3. Register the catch-all NL MessageHandler last.
        """
        ...

    async def _handle_nl_message(self, update, context) -> None:
        """Route natural language messages to agent.run(). Auto-commit after.
        Uses _send_long_message() to handle responses exceeding Telegram's 4096-char limit.
        """
        ...

    @staticmethod
    async def _send_long_message(target, text: str, **kwargs) -> None:
        """
        Split text into ≤4096-char chunks at line boundaries and send each as a
        separate message. `target` is an Update.message or telegram.Bot + chat_id.

        Used by _handle_nl_message, command handler callbacks, and WorkerScheduler
        for scheduled prompt responses.
        """
        MAX_LEN = 4096
        while text:
            if len(text) <= MAX_LEN:
                chunk, text = text, ""
            else:
                # Split at last newline before MAX_LEN
                split_at = text.rfind("\n", 0, MAX_LEN)
                if split_at == -1:
                    split_at = MAX_LEN
                chunk, text = text[:split_at], text[split_at:].lstrip("\n")
            await target.reply_text(chunk, **kwargs) if hasattr(target, "reply_text") else None
            # For bot + chat_id usage (scheduler): await bot.send_message(chat_id=chat_id, text=chunk)
        ...

    async def _auto_commit(self, reason: str) -> None:
        """
        git add commands/ memory/ hive.toml dashboard/ && git commit -m "hive: auto-commit after <reason>"
        Runs as async subprocess. Skips silently if nothing to commit.
        Protected by self._commit_lock to prevent concurrent git operations
        (e.g., simultaneous user message and scheduler job).

        Note: Scheduler jobs also trigger auto-commit via the callback passed to WorkerScheduler.
        """
        async with self._commit_lock:
            ...
```

---

## 7. shared/registry.py — Worker Registry

```python
# src/hive/shared/registry.py
import json
from pathlib import Path
from hive.shared.models import WorkerEntry

REGISTRY_FILE = Path.home() / ".config" / "hive" / "workers.json"

class HiveRegistry:
    """Read/write ~/.config/hive/workers.json — the source of truth for registered Workers."""

    def load(self) -> list[WorkerEntry]: ...
    def register(self, name: str, path: Path) -> None: ...
    def unregister(self, name: str) -> None: ...
    def get(self, name: str) -> WorkerEntry | None: ...
```

Registry file format:
```json
{
  "workers": [
    { "name": "budget", "path": "/Users/you/workers/budget" },
    { "name": "news",   "path": "/Users/you/workers/news"   }
  ]
}
```

---

## 8. shared/supervisor.py

```python
# src/hive/shared/supervisor.py
from pathlib import Path
import subprocess, shutil

SUPERVISORD_CONF     = Path.home() / ".config" / "hive" / "supervisord.conf"
SUPERVISORD_CONF_DIR = Path.home() / ".config" / "hive" / "conf.d"
LAUNCHAGENT_PLIST    = Path.home() / "Library" / "LaunchAgents" / "com.hive.supervisord.plist"

def ensure_supervisord_conf() -> None:
    """
    Create base supervisord.conf if absent.
    Includes [unix_http_server], [supervisord], [supervisorctl],
    [rpcinterface:supervisor], and [include] pointing to conf.d/*.conf.
    Creates conf.d/ directory.
    """
    ...

def write_worker_block(worker_name: str, worker_dir: Path) -> Path:
    """
    Write conf.d/<worker_name>.conf with supervisord program block.
    Returns path to written file. Idempotent.
    """
    ...

def write_comb_block(port: int = 8080) -> Path:
    """
    Write conf.d/hive-comb.conf for the Comb dashboard server.
    Called once by hive init on first use, alongside install_launchagent().
    Idempotent — safe to call again if the file already exists.
    """
    ...

def remove_worker_block(worker_name: str) -> None:
    """Delete conf.d/<worker_name>.conf if it exists."""
    ...

def reload_supervisord() -> None:
    """supervisorctl reread && supervisorctl update"""
    subprocess.run(["supervisorctl", "reread"], check=True)
    subprocess.run(["supervisorctl", "update"], check=True)

def supervisorctl(*args: str) -> subprocess.CompletedProcess:
    """Thin wrapper around supervisorctl. Caller checks returncode."""
    return subprocess.run(["supervisorctl", *args], capture_output=True, text=True)

def install_launchagent() -> None:
    """Write plist to ~/Library/LaunchAgents/ and load via launchctl. Idempotent."""
    ...

def is_launchagent_installed() -> bool:
    return LAUNCHAGENT_PLIST.exists()
```

Design: each Worker gets its own `conf.d/<name>.conf` (not a block in the monolithic file). Add/remove is atomic and avoids config-parse fragility. The base `supervisord.conf` uses `[include] files = conf.d/*.conf`.

---

## 9. cli/app.py

```python
# src/hive/cli/app.py
import typer
from pathlib import Path

app = typer.Typer(name="hive", help="Hive — local-first Telegram bot framework.")

@app.command()
def init(
    name: str = typer.Argument(..., help="Name for the new Worker"),
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Parent directory"),
) -> None:
    """Scaffold a new Worker folder. Register with supervisord. Install LaunchAgent + Comb on first use."""
    # On first use (LaunchAgent not yet installed):
    #   1. ensure_supervisord_conf()
    #   2. write_comb_block()        ← Comb registered once, globally
    #   3. install_launchagent()
    #   4. reload_supervisord()
    # Always (skip files that already exist — idempotent):
    #   5. mkdir -p <name>/{commands,memory,logs,dashboard}
    #   6. git init (skip if .git already exists)
    #   7. python -m venv .venv      ← bare venv, no pre-installed packages
    #   8. Write hive.toml template (skip if exists)
    #   9. Write .env template (skip if exists)
    #  10. Write requirements.txt template (skip if exists)
    #  11. Write .gitignore (.env, .venv/, logs/, *.pyc, __pycache__/, *.tmp, .DS_Store)
    #  12. write_worker_block(name, path)
    #  13. HiveRegistry.register(name, path)
    #  14. reload_supervisord()     ← autostart=true starts the Worker automatically
    ...

@app.command()
def start(path: Path = typer.Argument(...)) -> None:
    """Write/update supervisord block, register if needed, and start the Worker.

    Safe to call on workers not previously init-ed (e.g., cloned from git),
    provided the folder contains a valid hive.toml and .env. Idempotent.

    # 1. load_worker_config(path)           ← validates hive.toml + .env present
    # 2. Name reconciliation: if hive.toml name differs from existing supervisord
    #    block or registry entry for this path, remove the stale block/entry first,
    #    then proceed with the current name. hive.toml is always authoritative.
    # 3. write_worker_block(name, path)     ← idempotent
    # 4. HiveRegistry.register(name, path) ← idempotent
    # 5. reload_supervisord()
    # 6. supervisorctl start <worker_name>  ← reports "already running" gracefully
    """
    ...

@app.command()
def stop(path: Path = typer.Argument(...)) -> None:
    """Stop the Worker via supervisorctl."""
    ...

@app.command()
def remove(
    path: Path = typer.Argument(...),
    delete: bool = typer.Option(False, "--delete", help="Also delete the worker folder (irreversible)"),
) -> None:
    """Stop and unregister a Worker. The folder is kept unless --delete is passed.

    # 1. load_worker_config(path)            ← resolve worker name
    # 2. supervisorctl stop <worker_name>    ← tolerates "not running"
    # 3. remove_worker_block(worker_name)    ← no-op if absent
    # 4. HiveRegistry.unregister(name)       ← no-op if not registered
    # 5. reload_supervisord()
    # 6. [--delete only] prompt confirmation → shutil.rmtree(path)
    """
    ...

@app.command()
def restart(path: Path = typer.Argument(...)) -> None:
    """Restart the Worker via supervisorctl."""
    ...

@app.command()
def status() -> None:
    """Show supervisorctl status for all Hive-managed programs."""
    ...

@app.command()
def logs(
    path: Path = typer.Argument(...),
    lines: int = typer.Option(50, "--lines", "-n"),
    follow: bool = typer.Option(False, "--follow", "-f"),
) -> None:
    """Tail Worker logs (logs/out.log)."""
    ...

@app.command()
def run(path: Path = typer.Argument(...)) -> None:
    """Internal: Worker entrypoint called by supervisord. Not for direct use."""
    import asyncio
    from hive.shared.config import load_worker_config, ConfigError
    from hive.worker.runtime import WorkerRuntime
    try:
        config = load_worker_config(path)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)
    runtime = WorkerRuntime(config)
    asyncio.run(runtime.run())

@app.command(hidden=True)
def comb(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
) -> None:
    """Internal: Comb dashboard server entrypoint called by supervisord. Not for direct use."""
    from hive.comb.server import serve
    serve(host=host, port=port)
```

---

## 10. comb/server.py

```python
# src/hive/comb/server.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from hive.shared.registry import HiveRegistry
from hive.shared.config import load_worker_config, WorkerConfig
from hive.comb.cells import render_file_cell, render_metric_cell, tail_log_file

import time

_worker_cache: dict[str, WorkerConfig] = {}
_worker_cache_time: float = 0.0
_WORKER_CACHE_TTL: float = 5.0  # seconds

def _load_workers() -> dict[str, WorkerConfig]:
    """
    Re-read HiveRegistry and load all worker configs. Cached with a 5-second TTL
    so that Workers added via `hive init` after Comb starts are discovered on the
    next request without requiring a Comb restart.
    """
    global _worker_cache, _worker_cache_time
    now = time.monotonic()
    if now - _worker_cache_time < _WORKER_CACHE_TTL and _worker_cache:
        return _worker_cache
    registry = HiveRegistry()
    workers: dict[str, WorkerConfig] = {}
    for entry in registry.load():
        try:
            cfg = load_worker_config(entry.path)
            workers[cfg.worker.name] = cfg
        except Exception:
            pass
    _worker_cache = workers
    _worker_cache_time = now
    return workers

app = FastAPI(title="Hive Comb", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=...)

# Routes
# GET /                                  → list all workers
# GET /workers/{name}                    → dashboard HTML
# GET /workers/{name}/cells/{i}          → JSON content (file, metric)
# GET /workers/{name}/cells/{i}/stream   → SSE (log cell)

async def _sse_log_generator(log_path: Path):
    """Async generator: open file, seek to end, yield SSE events as lines appear."""
    ...

def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    serve()
```

---

## 11. comb/cells.py

```python
# src/hive/comb/cells.py
import json
from pathlib import Path

class CellRenderError(Exception): ...

def render_file_cell(source: Path) -> str:
    """Return raw text content. Markdown rendered client-side (marked.js)."""
    ...

def render_metric_cell(source: Path, key: str) -> str:
    """Read JSON file, extract top-level key, return as string."""
    ...

def tail_log_file(source: Path, lines: int = 100) -> list[str]:
    """
    Return last N lines efficiently (seek from end of file).
    Used for initial page load. Returns [] if file absent.
    """
    ...
```

---

## 12. Startup Sequence — `hive run <path>`

1. **CLI dispatch** (`cli/app.py: run()`) — Typer parses path argument, calls `asyncio.run(runtime.run())`
2. **`runtime.run()`** — top-level entry point on the single event loop
3. **Config load** (`shared/config.py: load_worker_config()`)
   - Resolve path to absolute
   - `python-dotenv` loads `.env` into process env
   - `tomllib` parses `hive.toml`
   - Pydantic validates into `WorkerConfig`
   - Assert `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID` present
4. **Runtime construction** (`worker/runtime.py: WorkerRuntime(config)`)
   - Instantiate `CommandRegistry(config)`
5. **Command discovery** (`worker/commands.py: registry.discover()`)
   - Glob `commands/*.py`, parse YAML docstrings, build `CommandMeta` objects
6. **MCP server construction** (`registry.build_mcp_server()`)
7. **Agent instantiation** (`worker/agent.py: ClaudeAgentRunner(...)`)
   - Load existing sessions from `memory/.sessions.json`
8. **Telegram Application build** — `ApplicationBuilder().token(...).build()`
9. **Handler registration** (`runtime._register_handlers()`)
   - Built-in handlers first (`/reset`, `/help`) — from `worker/builtins.py`
   - Warn and skip any user command whose name collides with `BUILTIN_NAMES`
   - User-defined `CommandHandler`s from `registry.telegram_handlers()`
   - Catch-all NL `MessageHandler` last
10. **Non-blocking Telegram start** — `app.initialize()` → `app.start()` → `app.updater.start_polling()`
11. **Scheduler start** (`worker/scheduler.py: WorkerScheduler.start()`)
    - Register cron jobs; `AsyncIOScheduler.start()` is non-blocking
    - WorkerScheduler receives bot instance + allowed_user_id for sending scheduled prompt responses
12. **Signal handlers installed** — `loop.add_signal_handler(SIGTERM/SIGINT, shutdown_event.set)`
13. **Await shutdown event** — runtime blocks here; scheduler + Telegram polling run concurrently
14. **Shutdown** — scheduler stop → agent close → Telegram updater stop → app stop → app shutdown

---

## 13. Error Handling

| Error | Source | Handling |
|---|---|---|
| Command non-zero exit | `execute()` | Raises `CommandError(stderr)` → caught by Telegram callback → reply with stderr |
| Agent failure | `ClaudeAgentRunner.run()` | Caught in `_handle_nl_message` → log full traceback → terse reply to user |
| Scheduler job failure | APScheduler job | Job error listener logs; no Telegram notification (no user initiated it) |
| Config error at startup | `load_worker_config()` | Raises `ConfigError` → printed to stderr → `typer.Exit(1)` |
| Comb cell render error | `render_*` functions | Raises `CellRenderError` → 500 response → displayed inline in dashboard panel |
| Unrecognised Telegram user | Auth guard | Silent return (no reply — avoids bot enumeration) |

---

## 14. Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `typer` | `>=0.12` | CLI framework |
| `python-telegram-bot` | `>=21.0` | Telegram Bot API (async) |
| `pydantic` | `>=2.0` | Config/model validation |
| `python-dotenv` | `>=1.0` | Load `.env` secrets |
| `apscheduler` | `>=3.10,<4` | Cron scheduler (AsyncIOScheduler) |
| `pyyaml` | `>=6.0` | Parse YAML docstrings in command scripts |
| `claude-agent-sdk` | latest | Claude Agent SDK (concrete AgentRunner) |
| `fastapi` | `>=0.111` | Comb dashboard server |
| `uvicorn` | `>=0.29` | ASGI server for FastAPI |
| `jinja2` | `>=3.1` | HTML templates for Comb |
| `tomllib` | stdlib 3.11+ | Parse `hive.toml` (no extra package) |

---

## 15. Implementation Order

Build in this order — each stage is independently testable:

1. `shared/models.py` — pure data classes, no deps beyond pydantic
2. `shared/config.py` — load_worker_config(), ConfigError
3. `shared/registry.py` — HiveRegistry, workers.json
4. `shared/supervisor.py` — supervisord config, launchagent
5. `cli/app.py` — skeleton; `hive --help` works after this
6. `worker/commands.py` — CommandRegistry (discovery + execute)
7. `worker/agent.py` — AgentRunner ABC + ClaudeAgentRunner (include reset_session())
8. `worker/builtins.py` — built-in handlers (/reset, /help)
9. `worker/scheduler.py` — WorkerScheduler
10. `worker/runtime.py` — WorkerRuntime (all subsystems wired, _register_handlers())
11. `comb/cells.py` — cell rendering
12. `comb/server.py` — FastAPI app
13. CLI command bodies — `init`, `start`, `stop`, `restart`, `status`, `logs`
14. `pyproject.toml` — add all dependencies listed above
