"""Shared utility functions for the Worker runtime."""

from __future__ import annotations

import asyncio
import html
import re
from contextlib import asynccontextmanager, suppress

import mistune
from mistune.plugins.formatting import strikethrough as _strikethrough_plugin
from telegram.error import BadRequest


class _TelegramHTMLRenderer(mistune.HTMLRenderer):
    """Renders markdown to Telegram-compatible HTML (restricted tag subset)."""

    def strong(self, text: str) -> str:
        return f"<b>{text}</b>"

    def emphasis(self, text: str) -> str:
        return f"<i>{text}</i>"

    def strikethrough(self, text: str) -> str:
        return f"<s>{text}</s>"

    def paragraph(self, text: str) -> str:
        return text.rstrip() + "\n\n"

    def heading(self, text: str, level: int, **attrs) -> str:
        return f"<b>{text}</b>\n"

    def link(self, text: str, url: str, title: str | None = None) -> str:
        return f'<a href="{url}">{text or url}</a>'

    def list(self, text: str, ordered: bool, **attrs) -> str:
        return text + "\n"

    def list_item(self, text: str) -> str:
        return f"• {text.strip()}\n"

    def block_code(self, code: str, info: str | None = None) -> str:
        return f"<pre>{html.escape(code, quote=False)}</pre>\n"

    def block_quote(self, text: str) -> str:
        return f"<blockquote>{text.strip()}</blockquote>\n"

    def thematic_break(self) -> str:
        return "───────────\n"

    def linebreak(self) -> str:
        return "\n"

    def softbreak(self) -> str:
        return "\n"

    def image(self, text: str, url: str, title: str | None = None) -> str:
        return text or url


_md_parser = mistune.create_markdown(
    renderer=_TelegramHTMLRenderer(escape=True),
    plugins=[_strikethrough_plugin],
)


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
    """Convert markdown to Telegram-compatible HTML using an AST parser."""
    return (_md_parser(text) or "").strip()


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
        try:
            if hasattr(target, "reply_text"):
                await target.reply_text(chunk, **kwargs)
            else:
                bot, chat_id = target
                await bot.send_message(chat_id=chat_id, text=chunk, **kwargs)
        except BadRequest as e:
            if "parse entities" in str(e).lower() and kwargs.get("parse_mode") == "HTML":
                plain = html.unescape(re.sub(r"<[^>]+>", "", chunk))
                plain_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                if hasattr(target, "reply_text"):
                    await target.reply_text(plain, **plain_kwargs)
                else:
                    bot, chat_id = target
                    await bot.send_message(chat_id=chat_id, text=plain, **plain_kwargs)
            else:
                raise
