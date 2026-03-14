"""Tests for hive.worker.utils module."""

from __future__ import annotations

from unittest.mock import AsyncMock

from hive.worker.utils import send_long_message


# ---------------------------------------------------------------------------
# send_long_message
# ---------------------------------------------------------------------------


class TestSendLongMessageShort:
    async def test_short_text_single_message(self) -> None:
        target = AsyncMock()
        target.reply_text = AsyncMock()

        await send_long_message(target, "Hello, world!")

        target.reply_text.assert_awaited_once_with("Hello, world!")

    async def test_empty_string_sends_nothing(self) -> None:
        target = AsyncMock()
        target.reply_text = AsyncMock()

        await send_long_message(target, "")

        target.reply_text.assert_not_awaited()


class TestSendLongMessageSplitNewline:
    async def test_splits_at_newline_boundary(self) -> None:
        # Build text where the first 4096 chars contain newlines
        line = "A" * 100 + "\n"  # 101 chars per line
        # 40 lines = 4040 chars, 41 lines = 4141 chars (over 4096)
        text = line * 41  # 4141 chars total

        target = AsyncMock()
        target.reply_text = AsyncMock()

        await send_long_message(target, text)

        assert target.reply_text.await_count == 2
        first_chunk = target.reply_text.await_args_list[0][0][0]
        # Should have split at a newline boundary, chunk length <= 4096
        assert len(first_chunk) <= 4096
        # rfind("\n") finds the last newline before 4096
        # chunk is text[:split_at] which is shorter than unsplit text
        assert len(first_chunk) < len(text)


class TestSendLongMessageSplitNoNewline:
    async def test_splits_at_max_len_without_newlines(self) -> None:
        # Text with no newlines at all
        text = "B" * 5000

        target = AsyncMock()
        target.reply_text = AsyncMock()

        await send_long_message(target, text)

        assert target.reply_text.await_count == 2
        first_chunk = target.reply_text.await_args_list[0][0][0]
        assert len(first_chunk) == 4096
        second_chunk = target.reply_text.await_args_list[1][0][0]
        assert len(second_chunk) == 904


class TestSendLongMessageTupleTarget:
    async def test_bot_chat_id_tuple(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock()
        chat_id = 12345

        await send_long_message((bot, chat_id), "Hello via tuple!")

        bot.send_message.assert_awaited_once_with(
            chat_id=12345, text="Hello via tuple!"
        )

    async def test_bot_chat_id_tuple_with_kwargs(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock()

        await send_long_message(
            (bot, 999), "some text", parse_mode="Markdown"
        )

        bot.send_message.assert_awaited_once_with(
            chat_id=999, text="some text", parse_mode="Markdown"
        )
