# CLI Reference

The `hive` CLI is the primary interface for creating, managing, and inspecting Workers. All commands are invoked as `hive <command> [args]`. Workers are managed as supervisord processes; supervisord itself is installed once and started by launchd — at login by default (LaunchAgent), or at boot via `hive boot enable` (LaunchDaemon).

## `hive init <name>`

Scaffold a new Worker folder in the current directory.

```
hive init <name>
```

What it does:
1. On first use: installs supervisord configuration and a macOS LaunchAgent so supervisord starts on login. (To start at boot instead, run `hive boot enable` afterwards.)
2. Creates `<name>/` with subdirectories: `commands/`, `memory/`, `logs/`, `dashboard/`.
3. Runs `git init` (skipped if `.git` already exists).
4. Creates a `.venv` using the system Python (skipped if already exists).
5. Writes template files if they don't exist: `hive.toml`, `.env`, `requirements.txt`, `.gitignore`.
6. Registers the Worker with supervisord and reloads.

After running, edit `.env` to fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID` before starting the Worker.

```bash
hive init my-bot
cd my-bot
# edit .env
hive start .
```

## `hive start <path>`

Write the supervisord program block for the Worker, reload supervisord, and start the process.

```
hive start <path>
```

If the Worker's `name` in `hive.toml` has changed since it was last registered, `start` removes the stale supervisord entry and re-registers under the new name.

```bash
hive start ~/workers/my-bot
hive start .   # from inside the Worker folder
```

## `hive stop <path>`

Stop a running Worker process via supervisord.

```
hive stop <path>
```

The Worker folder is not modified. Use `hive start` to resume.

## `hive restart <path>`

Stop and restart a Worker process. Use this to apply changes to `hive.toml` or `.env`.

```
hive restart <path>
```

## `hive remove <path> [--delete]`

Unregister a Worker from supervisord and remove it from the Hive registry. The Worker process is stopped first.

```
hive remove <path>
hive remove <path> --delete
```

| Flag | Description |
|---|---|
| `--delete` | Also delete the Worker folder from disk. Prompts for confirmation before deleting. |

Without `--delete`, the folder remains on disk and can be re-registered with `hive start`.

## `hive status`

Show the supervisord status for all registered Workers (and the Comb server).

```
hive status
```

Output is the raw `supervisorctl status` output. Each line shows the process name, state (RUNNING, STOPPED, FATAL, etc.), and uptime.

## `hive upgrade`

Re-apply all process management configuration for the current installation. Run this after upgrading Hive, or if Workers fail to start after a system reboot.

```
hive upgrade
```

What it does:

1. Ensures `supervisord.conf` runs supervisord in foreground mode (`nodaemon=true`), required for correct launchd supervision. Migrates existing configs automatically.
2. In login mode: regenerates the macOS LaunchAgent plist (`~/Library/LaunchAgents/com.hive.supervisord.plist`) if it is missing the `EnvironmentVariables` section, so supervisord and its child processes inherit the user's `PATH`. In boot mode: compares the installed LaunchDaemon plist against the current environment and reports if it's outdated (refreshing needs sudo, so run `hive boot enable` to apply — `upgrade` itself never prompts for a password).
3. Rewrites every registered Worker's supervisord conf to use the absolute path to `hive`, so Workers start correctly under launchd's minimal environment.
4. Rewrites the Comb dashboard conf with the absolute `hive` path.
5. Signals supervisord to reload and apply all changes.

**When to run:**

- Workers aren't running after a Mac reboot (and you've logged in)
- After `uv tool install hive` or `uv tool upgrade hive` on a machine with existing Workers
- After any manual change to supervisord configs that may have reverted settings

```bash
hive upgrade
hive status   # verify all workers are RUNNING
```

If the problem is that Workers only come back *after you log in*, that's the LaunchAgent working as designed — use `hive boot enable` to start them at boot instead.

## `hive boot enable|disable|status`

Control whether supervisord (and therefore all Workers) starts at **boot** or at **login**.

```bash
hive boot enable    # switch to boot mode (requires sudo)
hive boot disable   # switch back to login mode (requires sudo)
hive boot status    # show the current mode
hive boot stage     # write the daemon plist for manual sudo install (scripted setups)
```

`enable` installs a system LaunchDaemon at `/Library/LaunchDaemons/com.hive.supervisord.plist` and removes the login LaunchAgent. The daemon runs supervisord as your user (`UserName` key), so sockets, logs, and Worker folders are unchanged. `disable` reverses the migration — you are never left with neither.

Requirements and caveats:

- `enable`/`disable` run `sudo` interactively; in non-interactive sessions they print the exact manual commands instead.
- Workers need an on-disk agent auth token to work before login — run `hive auth` once (see below). `enable` warns about Workers that would boot without one.
- With FileVault enabled, the daemon starts only after the disk is unlocked at the pre-boot screen.

Verify without rebooting:

```bash
sudo launchctl print system/com.hive.supervisord   # state = running
hive status                                        # workers RUNNING
```

## `hive auth [--token TOKEN] [--api-key] [--status]`

Store agent auth credentials for **all** Workers in the global Hive `.env`
(`~/.config/hive/.env`, created with `600` permissions). A Worker's own `.env`
can still override the global value.

```bash
claude setup-token        # mint a long-lived, subscription-billed token
hive auth                 # prompts for the token (hidden input)
hive auth --token sk-ant-oat01-...   # non-interactive
hive auth --api-key       # store an ANTHROPIC_API_KEY instead (API billing)
hive auth --status        # show which keys are set (values masked)
```

Why: without a stored token, Worker agents fall back to the interactive Claude
Code OAuth token, which expires 8 hours after your last interactive session and
cannot be refreshed by headless Workers — agents then fail with
`401 Invalid authentication credentials` until Claude Code is opened again.

Restart running Workers after setting a token: `hive restart <path>`.

## `hive logs <path> [-n <lines>] [-f]`

Tail the Worker's stdout log at `<worker>/logs/out.log`.

```
hive logs <path>
hive logs <path> -n 100
hive logs <path> -f
hive logs <path> -n 200 -f
```

| Flag | Default | Description |
|---|---|---|
| `-n <lines>` | 50 | Number of lines to show |
| `-f` | false | Follow the log (stream new lines as they arrive) |

Press `Ctrl+C` to stop following.

## `hive chat <path>`

Open an interactive TUI chat session with a Worker. Talk to the agent and run commands directly from the terminal — no Telegram bot required.

```
hive chat <path>
```

The TUI supports the same built-in commands as Telegram (`/reset`, `/help`, `/menu`, `/set`) plus `/exit` and `/quit` to leave. Worker commands from `commands/` are available as slash commands.

Telegram credentials (`.env` keys `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID`) are optional for `hive chat` — it works without any Telegram configuration.

The agent, session overrides, auto-commit, and config change detection all work the same as in the Telegram runtime. Markdown responses are rendered with Rich.

## `hive run <path>`

Internal command. This is the Worker entrypoint called by supervisord; it boots the `WorkerRuntime` and runs the async event loop.

```
hive run <path>
```

Do not call this directly. Use `hive start` to launch Workers through supervisord so process supervision, autorestart, and log capture are active.

## `hive comb start`

Start the Comb dashboard server via supervisord.

```
hive comb start
```

The Comb server is registered as `hive-comb` in supervisord. It is installed automatically on `hive init` and serves the web dashboard at `<host>:8080`.

## `hive comb stop`

Stop the Comb dashboard server.

```
hive comb stop
```

## `hive comb restart`

Restart the Comb dashboard server. Use this to apply Comb configuration changes.

```
hive comb restart
```

## `hive comb serve [--host HOST] [--port PORT]`

Internal command. Starts the Comb HTTP server process directly. Called by supervisord; not intended for manual use.

```
hive comb serve --host 0.0.0.0 --port 8080
```

| Option | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Interface to bind to |
| `--port` | (configured default) | Port to listen on |
