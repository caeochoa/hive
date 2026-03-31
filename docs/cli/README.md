# CLI Reference

The `hive` CLI is the primary interface for creating, managing, and inspecting Workers. All commands are invoked as `hive <command> [args]`. Workers are managed as supervisord processes; supervisord itself is installed once and runs as a macOS LaunchAgent.

## `hive init <name>`

Scaffold a new Worker folder in the current directory.

```
hive init <name>
```

What it does:
1. On first use: installs supervisord configuration and a macOS LaunchAgent so supervisord starts on login.
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
