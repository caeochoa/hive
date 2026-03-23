# Worker Internals

Reference for contributors working on the Worker runtime. Covers the shared utilities in `src/hive/worker/utils.py` that handlers and command scripts rely on.

---

## `typing_action(bot, chat_id)`

An async context manager that sends a "typing…" indicator to a Telegram chat while work is in progress. Refreshes every 4 seconds to stay within Telegram's ~5s expiry.

**Used in:** `_handle_nl_message` and command handlers to give users visual feedback during agent/script execution.

```python
async with typing_action(context.bot, update.effective_chat.id):
    response = await self._agent.run(...)
```

The typing indicator cancels automatically when the `async with` block exits, whether normally or via exception.

---

## `send_long_message(target, text, **kwargs)`

Sends a text message to Telegram, splitting it into ≤4096-character chunks at line boundaries if needed. Handles both `Update.message` objects and `(bot, chat_id)` tuples.

**Used in:** Any handler that sends agent responses or command output, since Telegram enforces a hard 4096-char limit per message.

```python
# From a Telegram update handler
await send_long_message(update.message, text, parse_mode="HTML")

# From a scheduled task (no update object)
await send_long_message((bot, chat_id), text)
```

When `parse_mode="HTML"`, unclosed `<pre>` tags are automatically balanced at chunk boundaries so code blocks aren't broken.

---

## `md_to_telegram_html(text)`

Converts standard Markdown to the HTML subset that Telegram's `parse_mode="HTML"` accepts. Handles: fenced code blocks (`<pre>`), inline code (`<code>`), bold, italic, strikethrough, links, and headers.

**Used in:** `_handle_nl_message` to render Claude's Markdown responses as formatted Telegram messages.

```python
formatted = md_to_telegram_html(response)
await send_long_message(update.message, formatted, parse_mode="HTML")
```

Fenced code block contents are HTML-escaped but not processed for inline patterns, so code with `*asterisks*` or `_underscores_` is rendered literally.

---

## Notes

- These utilities are internal to `hive.worker` — Worker command scripts don't import them directly.
- Command scripts write plain text to stdout; Hive handles formatting before sending to Telegram.
