"""Built-in Telegram command handlers (/reset, /help, /menu) and callback dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from hive.worker.agent import AgentRunner, ClaudeAgentRunner
    from hive.worker.commands import CommandRegistry
    from hive.shared.models import CommandMeta

BUILTIN_NAMES: set[str] = {"reset", "help", "menu", "set"}


def _is_executable(meta: CommandMeta) -> bool:
    """True if all args have defaults (or no args) — safe to run without user input."""
    return all(not arg.required for arg in meta.args)


def _build_keyboard(registry: CommandRegistry) -> InlineKeyboardMarkup | None:
    """Build a 2-column inline keyboard from all registered commands."""
    if not registry.commands:
        return None
    buttons = []
    for meta in registry.commands.values():
        if _is_executable(meta):
            buttons.append(InlineKeyboardButton(f"/{meta.name}", callback_data=f"exec:{meta.name}"))
        else:
            buttons.append(InlineKeyboardButton(f"/{meta.name}", callback_data=f"usage:{meta.name}"))
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def make_reset_handler(agent_runner: AgentRunner, allowed_user_ids: list[int]):
    """Return a /reset handler that clears the agent session."""

    async def handle(update, context) -> None:
        user = update.effective_user
        if user is None or user.id not in allowed_user_ids:
            return
        chat_id = update.effective_chat.id
        await agent_runner.reset_session(chat_id)
        await update.message.reply_text("Session reset. Starting fresh.")

    return handle


def make_help_handler(registry: CommandRegistry, builtin_names: set[str], allowed_user_ids: list[int]):
    """Return a /help handler listing all commands with an inline keyboard."""

    async def handle(update, context) -> None:
        user = update.effective_user
        if user is None or user.id not in allowed_user_ids:
            return

        lines = [
            "<b>Built-in commands:</b>",
            "/reset \u2014 Start a fresh conversation",
            "/help \u2014 Show this message",
            "/menu \u2014 Quick command launcher",
            "",
        ]

        keyboard = None
        if registry.commands:
            lines.append("<b>Worker commands:</b>")
            for meta in registry.commands.values():
                arg_parts = []
                for a in meta.args:
                    if a.required:
                        arg_parts.append(f"&lt;{a.name}&gt;")
                    else:
                        arg_parts.append(f"[{a.name}={a.default}]")
                arg_hint = (" " + " ".join(arg_parts)) if arg_parts else ""
                lines.append(f"/{meta.name}{arg_hint} \u2014 {meta.description}")
            keyboard = _build_keyboard(registry)

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    return handle


def make_menu_handler(registry: CommandRegistry, allowed_user_ids: list[int]):
    """Return a /menu handler showing a compact inline keyboard of all commands."""

    async def handle(update, context) -> None:
        user = update.effective_user
        if user is None or user.id not in allowed_user_ids:
            return
        keyboard = _build_keyboard(registry)
        if keyboard is None:
            await update.message.reply_text("No commands available.")
            return
        await update.message.reply_text("Commands:", reply_markup=keyboard)

    return handle


def make_callback_handler(registry: CommandRegistry, allowed_user_ids: list[int]):
    """Return a callback handler for inline keyboard button presses."""

    async def handle(update, context) -> None:
        from hive.worker.commands import CommandError
        from hive.worker.utils import send_long_message, md_to_telegram_html, typing_action

        query = update.callback_query
        user = query.from_user
        if user is None or user.id not in allowed_user_ids:
            await query.answer()
            return

        await query.answer()
        data: str = query.data or ""

        if data.startswith("exec:"):
            name = data[5:]
            meta = registry.commands.get(name)
            if meta is None:
                await query.message.reply_text(f"Command /{name} not found.")
                return
            args = {a.name: a.default for a in meta.args if a.default is not None}
            try:
                async with typing_action(context.bot, query.message.chat_id):
                    result = await registry.execute(meta, args)
                text = result or "(no output)"
                if meta.args:
                    defaults_str = " ".join(str(a.default) for a in meta.args if a.default is not None)
                    customize = f"/{meta.name}" + (f" {defaults_str}" if defaults_str else "")
                    text = text.rstrip("\n") + f"\n\n\U0001f4a1 Customize: {customize}"
                await send_long_message(query.message, md_to_telegram_html(text), parse_mode="HTML")
            except CommandError as exc:
                await send_long_message(query.message, f"Error: {exc.stderr}", parse_mode="HTML")

        elif data.startswith("usage:"):
            name = data[6:]
            meta = registry.commands.get(name)
            if meta is None:
                await query.message.reply_text(f"Command /{name} not found.")
                return
            parts = [f"/{meta.name}"]
            for a in meta.args:
                parts.append(f"[{a.name}={a.default}]" if not a.required else f"&lt;{a.name}&gt;")
            usage = " ".join(parts)
            await query.message.reply_text(
                f"<b>/{meta.name}</b> \u2014 {meta.description}\n\nUsage: <code>{usage}</code>",
                parse_mode="HTML",
            )

    return handle


_SET_USAGE = (
    "<b>/set</b> \u2014 Override session config for this conversation.\n\n"
    "<b>Usage:</b>\n"
    "  <code>/set model &lt;model-id&gt;</code> \u2014 e.g. claude-opus-4-6\n"
    "  <code>/set max_turns &lt;n&gt;</code>\n"
    "  <code>/set thinking_budget_tokens &lt;n&gt;</code>\n"
    "  <code>/set reset</code> \u2014 clear all overrides\n\n"
    "Overrides reset on /reset or worker restart."
)

_VALID_INT_KEYS = {"max_turns", "thinking_budget_tokens"}
_VALID_STR_KEYS = {"model"}
_VALID_KEYS = _VALID_INT_KEYS | _VALID_STR_KEYS


def make_set_handler(agent_runner: ClaudeAgentRunner, allowed_user_ids: list[int]):
    """Return a /set handler for direct session config overrides."""

    async def handle(update, context) -> None:
        user = update.effective_user
        if user is None or user.id not in allowed_user_ids:
            return

        chat_id = update.effective_chat.id
        text: str = update.message.text or ""
        # Strip the /set command prefix (handles /set@botname too)
        parts = text.split(maxsplit=1)
        args_str = parts[1].strip() if len(parts) > 1 else ""

        if not args_str:
            await update.message.reply_text(_SET_USAGE, parse_mode="HTML")
            return

        if args_str == "reset":
            agent_runner.clear_session_override(chat_id)
            await update.message.reply_text("Session overrides cleared. Using config defaults.")
            return

        tokens = args_str.split(maxsplit=1)
        if len(tokens) != 2:
            await update.message.reply_text(_SET_USAGE, parse_mode="HTML")
            return

        key, value = tokens
        if key not in _VALID_KEYS:
            valid = ", ".join(sorted(_VALID_KEYS))
            await update.message.reply_text(
                f"Unknown setting <code>{key}</code>. Valid settings: {valid}",
                parse_mode="HTML",
            )
            return

        if key in _VALID_INT_KEYS:
            try:
                parsed_value = int(value)
            except ValueError:
                await update.message.reply_text(
                    f"<code>{key}</code> must be an integer.", parse_mode="HTML"
                )
                return
        else:
            parsed_value = value

        agent_runner.set_session_override(chat_id, **{key: parsed_value})
        await update.message.reply_text(
            f"Session config updated: <code>{key}={parsed_value}</code>. "
            "Takes effect from the next message.",
            parse_mode="HTML",
        )

    return handle
