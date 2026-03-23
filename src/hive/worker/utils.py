"""Shared utility functions for the Worker runtime."""

from __future__ import annotations

import asyncio
import html
import re
from contextlib import asynccontextmanager, suppress


@asynccontextmanager
async def typing_action(bot, chat_id: int):
    """Periodically send typing action until the context exits."""

    async def _keep_typing():
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)  # refresh before Telegram's ~5s expiry

    task = asyncio.create_task(_keep_typing())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def md_to_telegram_html(text: str) -> str:
    """Convert standard markdown to Telegram-compatible HTML.

    Handles fenced code blocks, inline code, bold, italic, strikethrough,
    links, and headers. Code block contents are HTML-escaped but not
    processed for markdown patterns.
    """
    parts: list[str] = []
    last_end = 0

    # Process fenced code blocks first so their contents skip inline conversion
    fence_re = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
    for match in fence_re.finditer(text):
        before = text[last_end : match.start()]
        parts.append(_md_convert_inline(before))
        code_content = html.escape(match.group(1), quote=False)
        parts.append(f"<pre>{code_content}</pre>")
        last_end = match.end()

    parts.append(_md_convert_inline(text[last_end:]))
    return "".join(parts)


def _md_convert_inline(text: str) -> str:
    """Convert inline markdown patterns to Telegram HTML in a non-code segment."""
    # Escape HTML special chars (&, <, >) — quote=False to leave ' and " unescaped
    text = html.escape(text, quote=False)

    # Extract inline code spans into placeholders so their content isn't further processed
    placeholders: dict[str, str] = {}
    counter = [0]

    def store_code(m: re.Match) -> str:
        key = f"\x00{counter[0]}\x00"
        counter[0] += 1
        placeholders[key] = f"<code>{m.group(1)}</code>"
        return key

    text = re.sub(r"`([^`\n]+)`", store_code, text)

    # Bold: **text** then __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic: *text* then _text_ (after bold to avoid matching ** as two *)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)

    # Strikethrough: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Headers: # Heading → <b>Heading</b>
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Restore inline code placeholders
    for key, value in placeholders.items():
        text = text.replace(key, value)

    return text


def _balance_pre_tags(chunk: str, remainder: str) -> tuple[str, str]:
    """Close any open <pre> tags at the end of chunk and reopen them in remainder."""
    diff = chunk.count("<pre>") - chunk.count("</pre>")
    if diff > 0:
        chunk += "</pre>" * diff
        remainder = "<pre>" * diff + remainder
    return chunk, remainder


async def send_long_message(target, text: str, **kwargs) -> None:
    """Split text into <=4096-char chunks at line boundaries and send each."""
    MAX_LEN = 4096
    while text:
        if len(text) <= MAX_LEN:
            chunk, text = text, ""
        else:
            split_at = text.rfind("\n", 0, MAX_LEN)
            if split_at == -1:
                split_at = MAX_LEN
            chunk, text = text[:split_at], text[split_at:].lstrip("\n")
            if kwargs.get("parse_mode") == "HTML":
                chunk, text = _balance_pre_tags(chunk, text)
        if hasattr(target, "reply_text"):
            await target.reply_text(chunk, **kwargs)
        else:
            # target is (bot, chat_id) tuple
            bot, chat_id = target
            await bot.send_message(chat_id=chat_id, text=chunk, **kwargs)
