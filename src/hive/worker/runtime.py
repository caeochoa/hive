"""Main Worker runtime — wires commands, agent, Telegram, and scheduler together."""

from __future__ import annotations

import asyncio
import logging
import signal
from types import SimpleNamespace
from typing import TYPE_CHECKING

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from hive.shared.config import WorkerConfig
from hive.worker.builtins import BUILTIN_NAMES, make_help_handler, make_reset_handler
from hive.worker.commands import CommandRegistry
from hive.worker.agent import ClaudeAgentRunner
from hive.worker.utils import send_long_message

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class WorkerRuntime:
    """Orchestrates all Worker subsystems within a single async event loop."""

    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._registry = CommandRegistry(config)
        self._scheduler = None
        self._agent: ClaudeAgentRunner | None = None
        self._app = None
        self._shutdown_event: asyncio.Event | None = None
        self._commit_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Top-level lifecycle
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Top-level entry: start, install signal handlers, wait for shutdown, stop."""
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
        """Full startup sequence.

        1. Discover commands
        2. Build MCP server
        3. Create agent runner
        4. Build Telegram Application
        5. Register handlers
        6. Non-blocking Telegram start: initialize -> start -> start_polling
        7. Start scheduler
        """
        self._registry.discover()
        commands_mcp = self._registry.build_mcp_server()

        agent_config = SimpleNamespace(
            model=self._config.agent_model,
            system_prompt=self._config.agent_system_prompt
            or "You are a worker agent. Your world is this folder.",
            max_turns=self._config.agent_max_turns,
            memory_dir=self._config.agent_memory_dir,
        )
        sessions_file = (
            self._config.worker_dir / self._config.agent_memory_dir / ".sessions.json"
        )
        self._agent = ClaudeAgentRunner(
            agent_config, commands_mcp, sessions_file, self._config.worker_dir
        )

        self._app = ApplicationBuilder().token(self._config.telegram_bot_token).build()
        self._register_handlers()

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        # Lazy-import scheduler to avoid hard failure if apscheduler isn't installed
        from hive.worker.scheduler import WorkerScheduler  # noqa: WPS433

        bot = self._app.bot
        self._scheduler = WorkerScheduler(
            self._config,
            self._registry,
            self._agent,
            bot,
            self._config.telegram_allowed_user_id,
            self._auto_commit,
        )
        self._scheduler.start()

    async def stop(self) -> None:
        """Graceful shutdown: scheduler -> agent -> telegram."""
        if self._scheduler:
            self._scheduler.stop()
        if self._agent:
            await self._agent.close()
        if self._app:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #

    def _is_allowed(self, update) -> bool:
        """Auth guard: return True only if user matches allowed_user_id."""
        user = update.effective_user
        return user is not None and user.id == self._config.telegram_allowed_user_id

    # ------------------------------------------------------------------ #
    # Handler registration
    # ------------------------------------------------------------------ #

    def _register_handlers(self) -> None:
        """Register handlers: built-ins first, user commands, then catch-all NL handler."""
        # Built-in handlers
        reset_handler = make_reset_handler(self._agent, self._config.telegram_allowed_user_id)
        help_handler = make_help_handler(self._registry, BUILTIN_NAMES, self._config.telegram_allowed_user_id)
        self._app.add_handler(CommandHandler("reset", reset_handler))
        self._app.add_handler(CommandHandler("help", help_handler))

        # User command handlers (warn on collision with built-ins)
        for handler in self._registry.telegram_handlers():
            # CommandHandler stores its command names in a frozenset called `commands`
            cmd_names = handler.commands if hasattr(handler, "commands") else frozenset()
            if cmd_names & BUILTIN_NAMES:
                for name in cmd_names & BUILTIN_NAMES:
                    logger.warning(
                        "Command '%s' collides with built-in, skipping", name
                    )
                continue
            self._app.add_handler(handler)

        # Catch-all natural language handler
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_nl_message)
        )

    # ------------------------------------------------------------------ #
    # Natural language handler
    # ------------------------------------------------------------------ #

    async def _handle_nl_message(self, update, context) -> None:
        """Route NL messages to agent, reply, auto-commit."""
        if not self._is_allowed(update):
            return
        try:
            response = await self._agent.run(
                update.message.text,
                update.effective_chat.id,
                self._config.worker_dir,
            )
            await send_long_message(update.message, response)
        except Exception:
            logger.exception("Agent error")
            await update.message.reply_text("Something went wrong. Check the logs.")
        await self._auto_commit("agent turn")

    # ------------------------------------------------------------------ #
    # Auto-commit
    # ------------------------------------------------------------------ #

    async def _auto_commit(self, reason: str) -> None:
        """Git add + commit tracked paths. Skip if nothing to commit."""
        async with self._commit_lock:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "add",
                "commands/",
                "memory/",
                "hive.toml",
                "dashboard/",
                cwd=str(self._config.worker_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            proc = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--cached",
                "--quiet",
                cwd=str(self._config.worker_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode == 0:
                return  # Nothing to commit

            proc = await asyncio.create_subprocess_exec(
                "git",
                "commit",
                "-m",
                f"hive: auto-commit after {reason}",
                cwd=str(self._config.worker_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
