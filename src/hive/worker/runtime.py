"""Main Worker runtime — wires commands, agent, Telegram, and scheduler together."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from types import SimpleNamespace

from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from hive.shared.config import WorkerConfig
from hive.worker.agent import DEFAULT_SYSTEM_PROMPT, ClaudeAgentRunner
from hive.worker.builtin_tools import build_builtin_mcp_server
from hive.worker.builtins import (
    BUILTIN_NAMES,
    make_callback_handler,
    make_help_handler,
    make_menu_handler,
    make_reset_handler,
    make_set_handler,
)
from hive.worker.commands import CommandRegistry
from hive.worker.utils import md_to_telegram_html, send_long_message, typing_action

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
        self._restart_task: asyncio.Task | None = None

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

    def _build_system_prompt(self) -> str:
        """Build the agent system prompt, appending self-config instructions only when no custom prompt is set."""
        if self._config.agent_system_prompt:
            return self._config.agent_system_prompt
        return DEFAULT_SYSTEM_PROMPT

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
        command_names = list(self._registry._commands) if commands_mcp is not None else []

        agent_config = SimpleNamespace(
            model=self._config.agent_model,
            system_prompt=self._build_system_prompt(),
            max_turns=self._config.agent_max_turns,
            memory_dir=self._config.agent_memory_dir,
            thinking_budget_tokens=self._config.agent_thinking_budget_tokens,
        )
        sessions_file = (
            self._config.worker_dir / self._config.agent_memory_dir / ".sessions.json"
        )
        self._agent = ClaudeAgentRunner(
            agent_config, commands_mcp, command_names, sessions_file, self._config.worker_dir,
        )

        self._agent.set_builtins_mcp(build_builtin_mcp_server(self._agent))

        self._app = ApplicationBuilder().token(self._config.telegram_bot_token).build()
        self._register_handlers()

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        bot_commands = [
            BotCommand("reset", "Start a fresh conversation"),
            BotCommand("help", "Show available commands"),
            BotCommand("menu", "Quick command launcher"),
            BotCommand("set", "Override session config (model, max_turns, ...)"),
        ] + [
            BotCommand(m.name, m.description[:255])
            for m in self._registry.commands.values()
        ]
        await self._app.bot.set_my_commands(bot_commands)

        # Lazy-import scheduler to avoid hard failure if apscheduler isn't installed
        from hive.worker.scheduler import WorkerScheduler  # noqa: WPS433

        bot = self._app.bot
        self._scheduler = WorkerScheduler(
            self._config,
            self._registry,
            self._agent,
            bot,
            self._config.telegram_allowed_user_ids,
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
        return user is not None and user.id in self._config.telegram_allowed_user_ids

    # ------------------------------------------------------------------ #
    # Handler registration
    # ------------------------------------------------------------------ #

    def _register_handlers(self) -> None:
        """Register handlers: built-ins first, user commands, then catch-all NL handler."""
        # Built-in handlers
        reset_handler = make_reset_handler(self._agent, self._config.telegram_allowed_user_ids)
        help_handler = make_help_handler(self._registry, BUILTIN_NAMES, self._config.telegram_allowed_user_ids)
        menu_handler = make_menu_handler(self._registry, self._config.telegram_allowed_user_ids)
        callback_handler = make_callback_handler(self._registry, self._config.telegram_allowed_user_ids)
        set_handler = make_set_handler(self._agent, self._config.telegram_allowed_user_ids)
        self._app.add_handler(CommandHandler("reset", reset_handler))
        self._app.add_handler(CommandHandler("help", help_handler))
        self._app.add_handler(CommandHandler("menu", menu_handler))
        self._app.add_handler(CommandHandler("set", set_handler))
        self._app.add_handler(CallbackQueryHandler(callback_handler))

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
    # Config change detection and self-restart
    # ------------------------------------------------------------------ #

    def _snapshot_worker_paths(self) -> dict[Path, int]:
        """Return mtime_ns for hive.toml and all commands/*.py files.

        Note: change detection is only wired into _handle_nl_message (interactive turns).
        Scheduled agent_prompt tasks intentionally skip it to avoid unattended restarts
        mid-schedule — supervisord will restart with updated config on the next interactive turn.
        """
        paths: dict[Path, int] = {}
        toml = self._config.worker_dir / "hive.toml"
        if toml.exists():
            paths[toml] = toml.stat().st_mtime_ns
        commands_dir = self._config.worker_dir / "commands"
        if commands_dir.is_dir():
            for p in commands_dir.glob("*.py"):
                paths[p] = p.stat().st_mtime_ns
        return paths

    @staticmethod
    def _detect_worker_changes(before: dict[Path, int], after: dict[Path, int]) -> bool:
        """Return True if any path was added, removed, or modified."""
        if set(before) != set(after):
            return True
        return any(before[p] != after[p] for p in before)

    async def _delayed_restart(self, delay: float = 1.5) -> None:
        """Sleep briefly then send SIGTERM; supervisord will restart the process."""
        await asyncio.sleep(delay)
        logger.info("Sending SIGTERM for self-restart after config change")
        os.kill(os.getpid(), signal.SIGTERM)

    # ------------------------------------------------------------------ #
    # Natural language handler
    # ------------------------------------------------------------------ #

    async def _handle_nl_message(self, update, context) -> None:
        """Route NL messages to agent, reply, auto-commit, and restart if config changed."""
        if not self._is_allowed(update):
            return

        chat_id = update.effective_chat.id
        before = self._snapshot_worker_paths()

        try:
            async with typing_action(context.bot, chat_id):
                response = await self._agent.run(
                    update.message.text,
                    chat_id,
                    self._config.worker_dir,
                )
            await send_long_message(update.message, md_to_telegram_html(response), parse_mode="HTML")

            # Note: snapshot is taken inside the try block so that errors during
            # send_long_message (e.g. Telegram network failure) also skip the restart.
            # This is intentional: if we couldn't deliver the response, we don't know
            # whether the agent finished cleanly, so we err on the side of no restart.
            after = self._snapshot_worker_paths()
            if self._detect_worker_changes(before, after):
                logger.info("Worker config files changed — scheduling restart")
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text="Config updated. Restarting worker to apply changes...",
                )
                self._restart_task = asyncio.create_task(self._delayed_restart())
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
