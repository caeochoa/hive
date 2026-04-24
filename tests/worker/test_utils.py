"""Tests for hive.worker.utils module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import BadRequest

from hive.worker.utils import send_long_message, md_to_telegram_html


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


class TestMdToTelegramHtml:
    def test_plain_text_unchanged(self) -> None:
        assert md_to_telegram_html("Hello world") == "Hello world"

    def test_html_special_chars_escaped(self) -> None:
        assert md_to_telegram_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_bold_double_asterisk(self) -> None:
        assert md_to_telegram_html("**hello**") == "<b>hello</b>"

    def test_bold_double_underscore(self) -> None:
        assert md_to_telegram_html("__hello__") == "<b>hello</b>"

    def test_italic_single_asterisk(self) -> None:
        assert md_to_telegram_html("*hello*") == "<i>hello</i>"

    def test_italic_single_underscore(self) -> None:
        assert md_to_telegram_html("_hello_") == "<i>hello</i>"

    def test_bold_before_italic_no_conflict(self) -> None:
        assert md_to_telegram_html("**bold** and *italic*") == "<b>bold</b> and <i>italic</i>"

    def test_strikethrough(self) -> None:
        assert md_to_telegram_html("~~gone~~") == "<s>gone</s>"

    def test_inline_code(self) -> None:
        assert md_to_telegram_html("`code`") == "<code>code</code>"

    def test_inline_code_escapes_html(self) -> None:
        assert md_to_telegram_html("`a < b`") == "<code>a &lt; b</code>"

    def test_fenced_code_block(self) -> None:
        result = md_to_telegram_html("```\nprint('hi')\n```")
        assert result == "<pre>print('hi')\n</pre>"

    def test_fenced_code_block_with_language(self) -> None:
        result = md_to_telegram_html("```python\nx = 1\n```")
        assert result == "<pre>x = 1\n</pre>"

    def test_fenced_code_escapes_html(self) -> None:
        result = md_to_telegram_html("```\na < b\n```")
        assert result == "<pre>a &lt; b\n</pre>"

    def test_link(self) -> None:
        assert md_to_telegram_html("[click](https://example.com)") == '<a href="https://example.com">click</a>'

    def test_h1_header(self) -> None:
        assert md_to_telegram_html("# Heading") == "<b>Heading</b>"

    def test_h3_header(self) -> None:
        assert md_to_telegram_html("### Deep heading") == "<b>Deep heading</b>"

    def test_code_block_content_not_processed_as_markdown(self) -> None:
        result = md_to_telegram_html("```\n**not bold**\n```")
        assert result == "<pre>**not bold**\n</pre>"

    def test_inline_code_content_not_processed_as_markdown(self) -> None:
        result = md_to_telegram_html("`**not bold**`")
        assert result == "<code>**not bold**</code>"

    def test_mixed_content(self) -> None:
        text = "**Title**\n\nSome `code` here.\n\n```python\nx = 1\n```"
        result = md_to_telegram_html(text)
        assert "<b>Title</b>" in result
        assert "<code>code</code>" in result
        assert "<pre>x = 1\n</pre>" in result

    def test_crossed_span_nesting_regression(self) -> None:
        # Original bug: sequential regex passes could produce <b>...<i>...</b>...</i>
        # AST parser guarantees correct nesting by construction.
        result = md_to_telegram_html("**bold and _italic** end_")
        # Should not contain crossed tags — bold closes before italic opens
        assert "</b>" not in result or result.index("</b>") > result.index("<b>")

    def test_link_no_title_attribute(self) -> None:
        result = md_to_telegram_html('[text](https://example.com "hover")')
        assert 'title=' not in result
        assert result == '<a href="https://example.com">text</a>'

    def test_link_without_title(self) -> None:
        assert md_to_telegram_html("[click](https://example.com)") == '<a href="https://example.com">click</a>'


class TestBadRequestFallback:
    async def test_fallback_strips_html_and_retries(self) -> None:
        target = AsyncMock()
        target.reply_text = AsyncMock(
            side_effect=[BadRequest("Can't parse entities: ..."), None]
        )

        await send_long_message(target, "<b>hello &amp; world</b>", parse_mode="HTML")

        assert target.reply_text.await_count == 2
        plain_call = target.reply_text.await_args_list[1]
        plain_text = plain_call[0][0]
        assert plain_text == "hello & world"
        assert "parse_mode" not in plain_call[1]

    async def test_non_parse_entity_bad_request_reraises(self) -> None:
        target = AsyncMock()
        target.reply_text = AsyncMock(side_effect=BadRequest("Message is too long"))

        with pytest.raises(BadRequest, match="Message is too long"):
            await send_long_message(target, "some text", parse_mode="HTML")
