"""Shared utility functions for the Worker runtime."""

from __future__ import annotations


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
