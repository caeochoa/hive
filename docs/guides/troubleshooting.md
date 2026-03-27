# Troubleshooting

Common issues with diagnosis and fixes.

---

## Worker won't start

**Symptom:** `hive status` shows the Worker as `STOPPED` or `FATAL`. Telegram bot is unresponsive.

**Cause:** supervisord may not be running, the Telegram bot token is invalid, the `.env` file is missing, or the Worker's `.venv` was not set up correctly.

**Fix:**
1. Run `hive status` — if supervisord itself is not responding, run `hive init` to reinstall the LaunchAgent.
2. Check that `.env` exists in the Worker folder and contains valid values for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID`.
3. Run `hive logs <path>` to read the error. Authentication failures and missing env vars appear in the first few lines at startup.
4. If the `.venv` is missing or broken, re-run `hive init <name>` to recreate it.

---

## Agent not responding to messages

**Symptom:** Slash commands work, but natural language messages get no reply.

**Cause:** Your Telegram user ID is not in the allowed list, or the bot is not running.

**Fix:**
1. Verify `TELEGRAM_ALLOWED_USER_ID` in `.env` matches your actual Telegram user ID. Send `/start` to [@userinfobot](https://t.me/userinfobot) to get your ID.
2. For multiple users, the value must be comma-separated with no spaces: `111111111,222222222`.
3. Confirm the Worker is running with `hive status`.
4. Check `hive logs <path>` for any message routing errors.

---

## Command not appearing in /help or not working

**Symptom:** A script in `commands/` does not appear in `/help` or the agent cannot call it.

**Cause:** Docstring parse error. Common mistakes include missing `name` or `description` fields, an indented docstring (the opening `"""` must follow immediately after the shebang line or start of file), or invalid YAML syntax.

**Fix:**
1. Run the script directly to check for Python syntax errors: `.venv/bin/python commands/foo.py`
2. Check that the docstring starts at column 0 after the opening `"""` — indented docstrings are not parsed.
3. Ensure `name` and `description` are present.
4. Validate YAML syntax — colons and special characters in values must be quoted.
5. After fixing, restart the Worker: `hive restart <path>`

---

## Agent loops or hits max_turns

**Symptom:** The agent sends multiple tool calls in a row and eventually stops with a max turns error.

**Cause:** The agent hit the configured `max_turns` limit. This can happen with genuinely complex tasks, or when a command script returns unhelpful or repetitive output that causes the agent to retry.

**Fix:**
1. Increase the limit in `hive.toml` and restart: `max_turns = 20`
2. Or adjust it for your current session without restarting: `/set max_turns 20`
3. Review `hive logs <path>` to see which tools the agent was calling repeatedly. If a command script is returning errors or empty output, fix the script.
4. For complex tasks, consider enabling extended thinking: `/set thinking_budget_tokens 8000`

---

## Session not persisting / agent forgets context

**Symptom:** The agent does not remember previous conversations after a Worker restart.

**Cause:** Sessions normally persist in `memory/.sessions.json`. If this file was deleted, or if `/reset` was called, the session is gone.

**Fix:**
1. Check that `memory/.sessions.json` exists. If not, sessions were cleared — this is expected after a clean reinstall.
2. Verify that `memory/` is not listed in the Worker's `.gitignore` (it should not be).
3. Note: `/reset` intentionally clears the session for your chat. This is expected behavior.
4. Sessions do persist across normal Worker restarts (including self-config restarts) as long as the file is not deleted.

---

## Overrides reset unexpectedly

**Symptom:** Settings applied with `/set` (model, max_turns, etc.) are gone after a restart.

**Cause:** Session overrides are in-memory only. They do not survive any Worker restart, including self-config restarts triggered by the agent editing `hive.toml` or `commands/`.

**Fix:** To make a change permanent, edit `hive.toml` directly and restart the Worker. Use `/set` only for temporary, per-session adjustments.

---

## Comb cell showing "Error" or empty

**Symptom:** A dashboard cell shows an error banner or no content.

**Cause:** The `source` file does not exist, the `key` is missing from the JSON file, or the JSON file is malformed.

**Fix:**
1. Check that the `source` path exists relative to the Worker folder. Paths are relative — `logs/out.log` resolves to `<worker-dir>/logs/out.log`.
2. For `metric` and `status` cells, open the JSON file and verify the `key` field exists at the top level and the file is valid JSON.
3. For `log` cells, if the log file does not exist yet, the cell waits and shows a placeholder — this resolves once the file is created.
4. Check `hive logs <path>` for Comb server errors (look for lines containing `Cell render error`).

---

## Worker self-restarted unexpectedly

**Symptom:** The Worker restarted on its own without `hive restart` being called.

**Cause:** The agent edited `hive.toml` or a file in `commands/` during an interactive turn. Hive detects changes to these files and schedules a graceful self-restart so the new configuration takes effect. This is expected behavior for self-configuration.

**Fix:** This is not an error. Check the Worker's git log to see exactly what changed:

```bash
git -C ./my-worker log --oneline -5
git -C ./my-worker show HEAD
```

If the agent made an unintended change, revert it:

```bash
git -C ./my-worker revert HEAD
hive restart ./my-worker
```

---

## Reading logs

**Symptom:** Need to understand what the Worker is doing or diagnose an error.

**Fix:** Use `hive logs <path>` to inspect Worker output.

```bash
hive logs ./my-worker          # Last 50 lines
hive logs ./my-worker -n 200   # Last 200 lines
hive logs ./my-worker -f       # Follow live
```

Log format: `TIMESTAMP hive.worker.runtime LEVEL message`

Key patterns to look for:

| Pattern | Meaning |
|---|---|
| `[tool_use]` | Agent called a tool |
| `[tool_result]` | Tool returned a result |
| `[result]` | Agent produced a final response |
| `ERROR` | An error occurred — read the full line for details |
| `auto-commit` | Hive committed files after an agent turn |
