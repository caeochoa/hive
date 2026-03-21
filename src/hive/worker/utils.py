"""Shared utility functions for the Worker runtime."""

from __future__ import annotations

import html
import re


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
        if hasattr(target, "reply_text"):
            await target.reply_text(chunk, **kwargs)
        else:
            # target is (bot, chat_id) tuple
            bot, chat_id = target
            await bot.send_message(chat_id=chat_id, text=chunk, **kwargs)
