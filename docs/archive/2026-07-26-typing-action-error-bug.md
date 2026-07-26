# Bug: spurious "Something went wrong" message after successful agent reply

## Symptom

After the Hive Worker agent successfully answers a query and sends its reply
to Telegram, the user sometimes immediately receives a second, unrelated
message: **"Something went wrong. Check the logs."** — even though the real
answer was already delivered correctly.

Observed in worker logs at `2026-07-26 13:19:38`: the agent's reply was sent
via `sendMessage` (`200 OK`), and only after that did the error appear.

## Root cause

`_handle_nl_message` in `hive/src/hive/worker/runtime.py` wraps the entire
agent streaming loop in a single `async with typing_action(context.bot,
chat_id):` block, all inside one `try/except Exception`:

```python
try:
    async with typing_action(context.bot, chat_id):
        async for chunk in self._agent.stream(...):
            await send_long_message(target, chunk.to_telegram_html(), ...)
    ...
except Exception:
    logger.exception("Agent error")
    await update.message.reply_text("Something went wrong. Check the logs.")
```

`typing_action` (`hive/src/hive/worker/utils.py:65-79`) runs a background
task that calls `bot.send_chat_action(..., action="typing")` on a loop every
4 seconds to keep the "typing…" indicator alive. On `__aexit__`, it cancels
that task and then `await`s it:

```python
@asynccontextmanager
async def typing_action(bot, chat_id: int):
    async def _keep_typing():
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)

    task = asyncio.create_task(_keep_typing())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
```

If the *last* `send_chat_action` call happens to be in flight when the
`async with` block exits, cancellation races with the network call. A
transient network hiccup on that specific request (e.g. a momentary DNS/TLS
connect failure to `api.telegram.org`, `httpx.ConnectError`) propagates as an
uncaught exception out of the `finally: await task` in `typing_action`, i.e.
out of the `async with` block itself — **after** the real answer has already
been sent successfully.

That exception is caught by the outer `except Exception` in
`_handle_nl_message`, which logs "Agent error" and sends the user a bogus
follow-up message, even though nothing was actually wrong with the response.

This is purely a cosmetic/cleanup-path issue: the typing indicator is a
best-effort UX nicety, not part of the actual response delivery, so a
failure there should never be treated as an agent failure.

## Fix

Make the background typing task resilient to its own network errors instead
of letting them propagate through `typing_action`'s exit:

```python
async def _keep_typing():
    while True:
        with suppress(Exception):
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(4)
```

This way a single failed "typing" ping is silently skipped (optionally
logged at debug level) and doesn't get treated as an agent-turn failure by
the caller's `try/except` in `_handle_nl_message`.

File to change: `hive/src/hive/worker/utils.py` (`typing_action`,
around line 65-79).
