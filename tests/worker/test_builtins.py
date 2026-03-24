"""Tests for built-in Telegram command handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from hive.worker.builtins import make_reset_handler, make_help_handler, BUILTIN_NAMES


def _make_update(chat_id: int = 12345, user_id: int = 12345):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    return update


class TestBuiltinNames:
    def test_contains_reset_and_help(self):
        assert "reset" in BUILTIN_NAMES
        assert "help" in BUILTIN_NAMES


class TestResetHandler:
    @pytest.mark.asyncio
    async def test_calls_reset_session(self):
        agent = MagicMock()
        agent.reset_session = AsyncMock()
        handler = make_reset_handler(agent, allowed_user_ids=[12345])

        update = _make_update(chat_id=42)
        await handler(update, MagicMock())

        agent.reset_session.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_replies_confirmation(self):
        agent = MagicMock()
        agent.reset_session = AsyncMock()
        handler = make_reset_handler(agent, allowed_user_ids=[12345])

        update = _make_update()
        await handler(update, MagicMock())

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "reset" in text.lower()


class TestHelpHandler:
    @pytest.mark.asyncio
    async def test_shows_builtins(self):
        registry = MagicMock()
        type(registry).commands = PropertyMock(return_value={})
        handler = make_help_handler(registry, BUILTIN_NAMES, allowed_user_ids=[12345])

        update = _make_update()
        await handler(update, MagicMock())

        text = update.message.reply_text.call_args[0][0]
        assert "/reset" in text
        assert "/help" in text

    @pytest.mark.asyncio
    async def test_shows_user_commands(self):
        meta = MagicMock()
        meta.name = "summarise"
        meta.description = "Summarise recent activity"
        registry = MagicMock()
        type(registry).commands = PropertyMock(return_value={"summarise": meta})
        handler = make_help_handler(registry, BUILTIN_NAMES, allowed_user_ids=[12345])

        update = _make_update()
        await handler(update, MagicMock())

        text = update.message.reply_text.call_args[0][0]
        assert "/summarise" in text
        assert "Summarise recent activity" in text

    @pytest.mark.asyncio
    async def test_no_user_commands_section_when_empty(self):
        registry = MagicMock()
        type(registry).commands = PropertyMock(return_value={})
        handler = make_help_handler(registry, BUILTIN_NAMES, allowed_user_ids=[12345])

        update = _make_update()
        await handler(update, MagicMock())

        text = update.message.reply_text.call_args[0][0]
        assert "Worker commands" not in text

    @pytest.mark.asyncio
    async def test_uses_markdown_parse_mode(self):
        registry = MagicMock()
        type(registry).commands = PropertyMock(return_value={})
        handler = make_help_handler(registry, BUILTIN_NAMES, allowed_user_ids=[12345])

        update = _make_update()
        await handler(update, MagicMock())

        kwargs = update.message.reply_text.call_args[1]
        assert kwargs.get("parse_mode") == "HTML"


class TestResetHandlerAuth:
    @pytest.mark.asyncio
    async def test_ignores_disallowed_user(self):
        agent = MagicMock()
        agent.reset_session = AsyncMock()
        handler = make_reset_handler(agent, allowed_user_ids=[99999])

        update = _make_update(user_id=11111)  # wrong user
        await handler(update, MagicMock())

        agent.reset_session.assert_not_awaited()
        update.message.reply_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allows_correct_user(self):
        agent = MagicMock()
        agent.reset_session = AsyncMock()
        handler = make_reset_handler(agent, allowed_user_ids=[99999])

        update = _make_update(user_id=99999)
        await handler(update, MagicMock())

        agent.reset_session.assert_awaited_once()


class TestSetHandler:
    def _make_set_update(self, text: str, user_id: int = 12345):
        from hive.worker.builtins import make_set_handler
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user = MagicMock()
        update.effective_user.id = user_id
        update.message.text = text
        update.message.reply_text = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_invalid_model_rejected_immediately(self):
        """A model value that doesn't start with 'claude-' is rejected with an error."""
        from hive.worker.builtins import make_set_handler

        agent = MagicMock()
        agent.set_session_override = MagicMock()
        handler = make_set_handler(agent, allowed_user_ids=[12345])

        update = self._make_set_update("/set model gpt-4o")
        await handler(update, MagicMock())

        agent.set_session_override.assert_not_called()
        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "claude-" in text.lower()

    @pytest.mark.asyncio
    async def test_valid_model_accepted(self):
        """A model value starting with 'claude-' is accepted."""
        from hive.worker.builtins import make_set_handler

        agent = MagicMock()
        agent.set_session_override = MagicMock()
        handler = make_set_handler(agent, allowed_user_ids=[12345])

        update = self._make_set_update("/set model claude-opus-4-6")
        await handler(update, MagicMock())

        agent.set_session_override.assert_called_once_with(12345, model="claude-opus-4-6")


class TestHelpHandlerAuth:
    @pytest.mark.asyncio
    async def test_ignores_disallowed_user(self):
        registry = MagicMock()
        type(registry).commands = PropertyMock(return_value={})
        handler = make_help_handler(registry, BUILTIN_NAMES, allowed_user_ids=[99999])

        update = _make_update(user_id=11111)  # wrong user
        await handler(update, MagicMock())

        update.message.reply_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allows_correct_user(self):
        registry = MagicMock()
        type(registry).commands = PropertyMock(return_value={})
        handler = make_help_handler(registry, BUILTIN_NAMES, allowed_user_ids=[99999])

        update = _make_update(user_id=99999)
        await handler(update, MagicMock())

        update.message.reply_text.assert_awaited_once()
