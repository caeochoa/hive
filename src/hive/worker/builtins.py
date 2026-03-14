"""Built-in Telegram command handlers (/reset, /help)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hive.worker.agent import AgentRunner
    from hive.worker.commands import CommandRegistry

BUILTIN_NAMES: set[str] = {"reset", "help"}


def make_reset_handler(agent_runner: AgentRunner):
    """Return a /reset handler that clears the agent session."""

    async def handle(update, context) -> None:
        chat_id = update.effective_chat.id
        await agent_runner.reset_session(chat_id)
        await update.message.reply_text("Session reset. Starting fresh.")

    return handle


def make_help_handler(registry: CommandRegistry, builtin_names: set[str]):
    """Return a /help handler that lists all available commands."""

    async def handle(update, context) -> None:
        lines = [
            "*Built-in commands:*",
            "/reset \u2014 Start a fresh conversation",
            "/help \u2014 Show this message",
            "",
        ]
        if registry.commands:
            lines.append("*Worker commands:*")
            for meta in registry.commands.values():
                lines.append(f"/{meta.name} \u2014 {meta.description}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    return handle
