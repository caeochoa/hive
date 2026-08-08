"""Hive CLI — all commands."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(name="hive", help="Hive — local-first Telegram bot framework")

HIVE_TOML_TEMPLATE = """\
[worker]
name = "{name}"
hive_version = "{hive_version}"

[agent]
model = "claude-haiku-4-5"
memory_dir = "memory/"
max_turns = 10
"""

ENV_TEMPLATE = """\
TELEGRAM_BOT_TOKEN=
# One user: TELEGRAM_ALLOWED_USER_ID=12345
# Multiple users: TELEGRAM_ALLOWED_USER_ID=12345,67890
TELEGRAM_ALLOWED_USER_ID=
# Agent auth: run `hive auth` once to set a token for all Workers globally
# (get one with `claude setup-token`). Uncomment below only to override the
# global token for this Worker.
# CLAUDE_CODE_OAUTH_TOKEN=
# Alternative (API billing): ANTHROPIC_API_KEY=
"""

GITIGNORE_TEMPLATE = """\
.env
.venv/
logs/
*.pyc
__pycache__/
*.tmp
.DS_Store
"""

REQUIREMENTS_TEMPLATE = """\
# Add Worker-specific Python dependencies here.
# Install with: .venv/bin/pip install -r requirements.txt
"""


@app.command()
def init(name: str = typer.Argument(..., help="Name for the new Worker")) -> None:
    """Scaffold a new Worker folder. Register with supervisord. Install LaunchAgent + Comb on first use."""
    from hive import __version__
    from hive.shared.registry import HiveRegistry
    from hive.shared.supervisor import (
        ensure_supervisord_conf,
        install_launchagent,
        is_boot_config_installed,
        reload_supervisord,
        write_comb_block,
        write_worker_block,
    )

    worker_dir = Path.cwd() / name
    worker_dir = worker_dir.resolve()

    # First-use setup
    if not is_boot_config_installed():
        typer.echo("First-time setup: configuring supervisord and LaunchAgent...")
        ensure_supervisord_conf()
        write_comb_block()
        try:
            install_launchagent()
        except RuntimeError as e:
            typer.echo(f"Warning: {e}", err=True)
        reload_supervisord()
        typer.echo(
            "Tip: run 'hive boot enable' to start Workers at boot "
            "instead of at login (requires sudo)."
        )

    # Create directory structure
    for subdir in ("commands", "memory", "logs", "dashboard"):
        (worker_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Git init (skip if .git exists)
    if not (worker_dir / ".git").exists():
        subprocess.run(["git", "init", str(worker_dir)], capture_output=True)

    # Create .venv (skip if exists)
    if not (worker_dir / ".venv").exists():
        subprocess.run(
            [sys.executable, "-m", "venv", str(worker_dir / ".venv")],
            capture_output=True,
        )

    # Write template files (skip if exist)
    _write_if_missing(
        worker_dir / "hive.toml",
        HIVE_TOML_TEMPLATE.format(name=name, hive_version=__version__),
    )
    _write_if_missing(worker_dir / ".env", ENV_TEMPLATE)
    _write_if_missing(worker_dir / "requirements.txt", REQUIREMENTS_TEMPLATE)
    _write_if_missing(worker_dir / ".gitignore", GITIGNORE_TEMPLATE)

    # Register with supervisord
    write_worker_block(name, worker_dir)
    HiveRegistry().register(name, str(worker_dir))
    reload_supervisord()

    typer.echo(f"Worker '{name}' created at {worker_dir}")
    typer.echo("Edit .env to add your TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID")


def _warn_if_worker_behind(config) -> None:
    """Print a short note if a Worker's stamped hive_version is behind the installed Hive."""
    from hive import __version__
    from hive.shared.changelog import compare_versions

    if compare_versions(config.hive_version, __version__) == "behind":
        typer.echo(
            f"Note: '{config.name}' was scaffolded against Hive {config.hive_version}, "
            f"installed is {__version__}. Run 'hive update {config.worker_dir}' to see what changed."
        )


@app.command()
def start(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Start a Worker process."""
    from hive.shared.config import ConfigError, load_worker_config
    from hive.shared.registry import HiveRegistry
    from hive.shared.supervisor import (
        reload_supervisord,
        supervisorctl,
        write_worker_block,
    )

    worker_dir = Path(path).resolve()
    try:
        config = load_worker_config(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    name = config.name
    registry = HiveRegistry()

    # Name reconciliation: remove stale entries for this path
    for entry in registry.list_workers():
        if entry.path == str(worker_dir) and entry.name != name:
            from hive.shared.supervisor import remove_worker_block

            remove_worker_block(entry.name)
            registry.unregister(entry.name)

    write_worker_block(name, worker_dir)
    registry.register(name, str(worker_dir))
    reload_supervisord()

    result = supervisorctl("start", f"worker-{name}")
    typer.echo(result.stdout.strip() if result.stdout else f"Started worker-{name}")
    _warn_if_worker_behind(config)


@app.command()
def stop(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Stop a Worker process."""
    from hive.shared.config import ConfigError, load_worker_config
    from hive.shared.supervisor import supervisorctl

    worker_dir = Path(path).resolve()
    try:
        config = load_worker_config(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    result = supervisorctl("stop", f"worker-{config.name}")
    typer.echo(result.stdout.strip() if result.stdout else f"Stopped worker-{config.name}")


@app.command()
def restart(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Restart a Worker process."""
    from hive.shared.config import ConfigError, load_worker_config
    from hive.shared.supervisor import supervisorctl

    worker_dir = Path(path).resolve()
    try:
        config = load_worker_config(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    result = supervisorctl("restart", f"worker-{config.name}")
    typer.echo(result.stdout.strip() if result.stdout else f"Restarted worker-{config.name}")
    _warn_if_worker_behind(config)


@app.command()
def remove(
    path: str = typer.Argument(..., help="Path to Worker folder"),
    delete: bool = typer.Option(False, "--delete", help="Also delete the folder"),
) -> None:
    """Unregister and stop a Worker. Folder is kept unless --delete is passed."""
    from hive.shared.config import ConfigError, load_worker_config
    from hive.shared.registry import HiveRegistry
    from hive.shared.supervisor import (
        reload_supervisord,
        remove_worker_block,
        supervisorctl,
    )

    worker_dir = Path(path).resolve()
    try:
        config = load_worker_config(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    name = config.name
    supervisorctl("stop", f"worker-{name}")
    remove_worker_block(name)
    HiveRegistry().unregister(name)
    reload_supervisord()

    typer.echo(f"Worker '{name}' unregistered")

    if delete:
        typer.confirm(f"Delete folder {worker_dir}?", abort=True)
        shutil.rmtree(worker_dir)
        typer.echo(f"Deleted {worker_dir}")


@app.command()
def status() -> None:
    """Show status of all Workers."""
    from hive import __version__
    from hive.shared.changelog import compare_versions
    from hive.shared.config import ConfigError, load_worker_config_for_tui
    from hive.shared.registry import HiveRegistry
    from hive.shared.supervisor import supervisorctl

    result = supervisorctl("status")
    if result.stdout:
        typer.echo(result.stdout.strip())
    else:
        typer.echo("No workers running")

    behind = []
    for entry in HiveRegistry().list_workers():
        try:
            config = load_worker_config_for_tui(Path(entry.path))
        except ConfigError:
            continue
        if compare_versions(config.hive_version, __version__) == "behind":
            behind.append((entry.name, config.hive_version))

    if behind:
        typer.echo(f"\nWorkers behind installed Hive ({__version__}):")
        for name, worker_version in behind:
            typer.echo(f"  ⚠ {name} ({worker_version}) — run 'hive update <path>' for details")


@app.command()
def logs(
    path: str = typer.Argument(..., help="Path to Worker folder"),
    lines: int = typer.Option(50, "-n", help="Number of lines"),
    follow: bool = typer.Option(False, "-f", help="Follow log"),
) -> None:
    """Tail Worker logs."""
    worker_dir = Path(path).resolve()
    log_file = worker_dir / "logs" / "out.log"
    if not log_file.exists():
        typer.echo(f"Log file not found: {log_file}", err=True)
        raise typer.Exit(code=1)

    cmd = ["tail", f"-n{lines}"]
    if follow:
        cmd.append("-f")
    cmd.append(str(log_file))

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


@app.command()
def run(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """[Internal] Worker entrypoint called by supervisord."""
    import asyncio
    import logging

    from hive.shared.config import ConfigError, load_worker_config
    from hive.worker.runtime import WorkerRuntime

    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    worker_dir = Path(path).resolve()
    try:
        config = load_worker_config(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    runtime = WorkerRuntime(config)
    asyncio.run(runtime.run())


@app.command()
def chat(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Open an interactive TUI chat session with a Worker."""
    import asyncio

    from hive.shared.config import ConfigError, load_worker_config_for_tui
    from hive.worker.tui import run_tui

    worker_dir = Path(path).resolve()
    try:
        config = load_worker_config_for_tui(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    asyncio.run(run_tui(config))


@app.command()
def repair() -> None:
    """Re-apply process management config. Run after upgrading Hive or if workers don't start after reboot."""
    from hive.shared import supervisor
    from hive.shared.registry import HiveRegistry
    from hive.shared.supervisor import (
        ensure_supervisord_conf,
        install_launchagent,
        is_launchdaemon_installed,
        reload_supervisord,
        write_comb_block,
        write_worker_block,
    )

    typer.echo("Repairing Hive process-management configuration...")

    ensure_supervisord_conf()
    typer.echo("  supervisord.conf: OK")

    if is_launchdaemon_installed():
        # Boot mode: refreshing the daemon plist needs sudo, so only report drift
        try:
            desired = supervisor.render_launchdaemon_plist()
        except RuntimeError as e:
            typer.echo(f"  Warning: {e}", err=True)
            desired = None
        if desired is not None and supervisor.LAUNCHDAEMON_PLIST.read_text() != desired:
            typer.echo(
                "  LaunchDaemon: outdated — run 'hive boot enable' to refresh (requires sudo)"
            )
        else:
            typer.echo("  LaunchDaemon: OK")
    else:
        try:
            install_launchagent()
            typer.echo("  LaunchAgent: OK")
        except RuntimeError as e:
            typer.echo(f"  Warning: {e}", err=True)

    registry = HiveRegistry()
    for entry in registry.list_workers():
        write_worker_block(entry.name, Path(entry.path))
        typer.echo(f"  worker-{entry.name}: conf updated")

    write_comb_block()
    typer.echo("  hive-comb: conf updated")

    reload_supervisord()
    typer.echo("Done. Run 'hive status' to verify.")


@app.command()
def version() -> None:
    """Print the installed Hive version."""
    from hive import __version__

    typer.echo(__version__)


_HIVE_VERSION_LINE_RE = re.compile(r'(?m)^hive_version[ \t]*=[ \t]*"[^"]*"[ \t]*$')


def _bump_worker_hive_version(worker_dir: Path, new_version: str) -> None:
    """Rewrite (or insert) the `hive_version` field in a Worker's hive.toml in place."""
    toml_path = worker_dir / "hive.toml"
    text = toml_path.read_text()
    new_line = f'hive_version = "{new_version}"'
    if _HIVE_VERSION_LINE_RE.search(text):
        text = _HIVE_VERSION_LINE_RE.sub(new_line, text, count=1)
    else:
        text = re.sub(r"(?m)^\[worker\]\s*$", f"[worker]\n{new_line}", text, count=1)
    toml_path.write_text(text)


@app.command()
def update(
    path: str = typer.Argument(..., help="Path to Worker folder"),
    bump: bool = typer.Option(
        False,
        "--bump",
        help="After reviewing the drift, record the installed Hive version as this Worker's new baseline",
    ),
) -> None:
    """Report what's changed in Hive since this Worker was scaffolded.

    Only writes to the Worker when `--bump` is passed (updates hive_version in
    hive.toml); otherwise read-only. Unrelated to `hive repair`, which
    re-applies process manager (supervisord/LaunchAgent) configuration.
    """
    from hive import __version__
    from hive.shared.changelog import (
        GITHUB_CHANGELOG_URL,
        compare_versions,
        entries_between,
        find_changelog_text,
        parse_changelog,
    )
    from hive.shared.config import ConfigError, load_worker_config_for_tui

    worker_dir = Path(path).resolve()

    try:
        config = load_worker_config_for_tui(worker_dir)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1)

    worker_version = config.hive_version
    typer.echo(f"Installed Hive version: {__version__}")

    drift = compare_versions(worker_version, __version__)
    if worker_version is None:
        typer.echo(
            f"Worker '{config.name}' has no recorded hive_version "
            "(scaffolded before version stamping was introduced) — treating as unknown baseline."
        )
    else:
        typer.echo(f"Worker '{config.name}' scaffolded against: {worker_version}")
        if drift == "match":
            typer.echo("Worker is up to date with the installed Hive version.")
        elif drift == "ahead":
            typer.echo(
                "Worker's recorded hive_version is newer than the installed Hive "
                "(unusual — was it edited manually, or did you downgrade Hive?)."
            )
        elif drift == "behind":
            typer.echo("Worker is behind the installed Hive version.")
        else:
            typer.echo(
                f"Warning: could not compare '{worker_version}' and '{__version__}' as versions "
                "— skipping drift check.",
                err=True,
            )

    changelog_text = find_changelog_text()
    if changelog_text is None:
        typer.echo(f"\nCHANGELOG.md not available locally — see {GITHUB_CHANGELOG_URL}")
    else:
        relevant = entries_between(parse_changelog(changelog_text), worker_version, __version__)
        if not relevant:
            typer.echo("\nNo recorded changes between these versions.")
        else:
            typer.echo("\nChanges since this Worker was scaffolded:\n")
            for entry in relevant:
                header = f"## [{entry.version}]" + (f" - {entry.date}" if entry.date else "")
                typer.echo(header)
                typer.echo(entry.body)
                typer.echo("")

    if bump:
        _bump_worker_hive_version(worker_dir, __version__)
        typer.echo(f"\nRecorded hive_version = \"{__version__}\" in {worker_dir / 'hive.toml'}.")


def _upsert_env_var(path: Path, key: str, value: str) -> None:
    """Set key=value in a dotenv file, replacing an existing line or appending."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    new_line = f"{key}={value}"
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def _mask_secret(value: str) -> str:
    if len(value) <= 16:
        return "****"
    return f"{value[:12]}…{value[-4:]}"


@app.command()
def auth(
    token: str = typer.Option(
        None,
        "--token",
        help=(
            "The token to store (prompted if omitted). Avoid this flag in scripts — "
            "the value lands in shell history and is visible to other local users via "
            "`ps`. Prefer piping it on stdin instead, e.g. `echo \"$TOKEN\" | hive auth`."
        ),
    ),
    api_key: bool = typer.Option(False, "--api-key", help="Store as ANTHROPIC_API_KEY (API billing) instead of CLAUDE_CODE_OAUTH_TOKEN"),
    status: bool = typer.Option(False, "--status", help="Show which auth keys are set globally"),
) -> None:
    """Store agent auth for all Workers in the global Hive .env.

    Get a long-lived, subscription-billed token by running `claude setup-token`.
    Workers can still override this in their own .env.
    """
    from dotenv import dotenv_values

    from hive.shared.config import AGENT_ENV_KEYS, GLOBAL_ENV_PATH

    if status:
        env = dotenv_values(GLOBAL_ENV_PATH) if GLOBAL_ENV_PATH.exists() else {}
        typer.echo(f"Global auth file: {GLOBAL_ENV_PATH}")
        for key in AGENT_ENV_KEYS:
            value = env.get(key)
            typer.echo(f"  {key}: {_mask_secret(value) if value else 'not set'}")
        return

    key = "ANTHROPIC_API_KEY" if api_key else "CLAUDE_CODE_OAUTH_TOKEN"
    if token is None:
        typer.echo("Tip: run `claude setup-token` to mint a long-lived subscription token.")
        token = typer.prompt(f"{key}", hide_input=True)
    token = token.strip()
    if not token:
        typer.echo("Error: empty token", err=True)
        raise typer.Exit(code=1)

    _upsert_env_var(GLOBAL_ENV_PATH, key, token)
    typer.echo(f"Saved {key} to {GLOBAL_ENV_PATH}")
    typer.echo("Applies to all Workers (their own .env takes precedence).")
    typer.echo("Run 'hive restart <path>' on running Workers to apply.")


boot_app = typer.Typer(
    help="Manage starting Hive at boot (LaunchDaemon) vs at login (LaunchAgent)."
)
app.add_typer(boot_app, name="boot")


def _run_sudo(args: list[str]) -> subprocess.CompletedProcess:
    """Run a command under sudo, inheriting the TTY so the password prompt works."""
    return subprocess.run(["sudo", *args])


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _warn_workers_without_auth_token() -> None:
    """Warn about Workers whose agent has no on-disk auth token.

    Without one, their agent falls back to interactive Claude Code credentials,
    which don't exist before the user logs in.
    """
    from dotenv import dotenv_values

    from hive.shared.config import resolve_agent_env
    from hive.shared.registry import HiveRegistry

    missing = []
    for entry in HiveRegistry().list_workers():
        env_path = Path(entry.path) / ".env"
        worker_env = dotenv_values(env_path) if env_path.exists() else {}
        if not resolve_agent_env(worker_env):
            missing.append(entry.name)
    if missing:
        typer.echo(
            f"Warning: no agent auth token found for: {', '.join(missing)}. "
            "Their agents rely on interactive Claude Code credentials, which are "
            "unavailable at boot. Run 'hive auth' once (token from `claude setup-token`).",
            err=True,
        )


@boot_app.command("enable")
def boot_enable() -> None:
    """Start supervisord at boot via a system LaunchDaemon (requires sudo)."""
    from hive.shared import supervisor
    from hive.shared.supervisor import (
        ensure_supervisord_conf,
        install_launchdaemon,
        is_launchdaemon_installed,
    )

    if is_launchdaemon_installed():
        try:
            if supervisor.LAUNCHDAEMON_PLIST.read_text() == supervisor.render_launchdaemon_plist():
                typer.echo("Boot mode already enabled.")
                _warn_workers_without_auth_token()
                return
        except RuntimeError:
            pass  # supervisord missing from PATH; fall through to reinstall

    if not _stdin_is_tty():
        staged = supervisor.LAUNCHDAEMON_STAGED
        plist = supervisor.LAUNCHDAEMON_PLIST
        typer.echo(
            "Cannot prompt for sudo in a non-interactive session. "
            "Run 'hive boot enable' in a terminal, or run these commands manually:"
        )
        typer.echo(f"  hive boot stage   # writes {staged}")
        typer.echo(f"  sudo launchctl bootout system/{supervisor.LAUNCHD_LABEL}")
        typer.echo(f"  sudo install -o root -g wheel -m 644 {staged} {plist}")
        typer.echo(f"  sudo launchctl bootstrap system {plist}")
        typer.echo(f"  sudo launchctl enable system/{supervisor.LAUNCHD_LABEL}")
        raise typer.Exit(code=1)

    typer.echo(
        "Installing a system LaunchDaemon so Workers start at boot "
        "(sudo will prompt for your password)..."
    )
    ensure_supervisord_conf()
    try:
        install_launchdaemon(_run_sudo)
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo("Boot mode enabled: supervisord now starts at boot, before login.")
    _warn_workers_without_auth_token()
    typer.echo("Run 'hive status' to verify Workers are running.")


@boot_app.command("stage")
def boot_stage() -> None:
    """Write the LaunchDaemon plist to the staging path (for manual sudo install)."""
    from hive.shared import supervisor

    supervisor.LAUNCHDAEMON_STAGED.parent.mkdir(parents=True, exist_ok=True)
    supervisor.LAUNCHDAEMON_STAGED.write_text(supervisor.render_launchdaemon_plist())
    typer.echo(f"Staged LaunchDaemon plist at {supervisor.LAUNCHDAEMON_STAGED}")


@boot_app.command("disable")
def boot_disable() -> None:
    """Remove the boot LaunchDaemon and restore the login LaunchAgent (requires sudo)."""
    from hive.shared import supervisor
    from hive.shared.supervisor import (
        install_launchagent,
        reload_supervisord,
        uninstall_launchdaemon,
    )

    if not _stdin_is_tty():
        typer.echo(
            "Cannot prompt for sudo in a non-interactive session. "
            "Run 'hive boot disable' in a terminal, or run these commands manually:"
        )
        typer.echo(f"  sudo launchctl bootout system/{supervisor.LAUNCHD_LABEL}")
        typer.echo(f"  sudo rm -f {supervisor.LAUNCHDAEMON_PLIST}")
        typer.echo("  hive repair   # reinstalls the login LaunchAgent")
        raise typer.Exit(code=1)

    uninstall_launchdaemon(_run_sudo)
    try:
        install_launchagent()
    except RuntimeError as e:
        typer.echo(f"Warning: {e}", err=True)
    reload_supervisord()
    typer.echo("Boot mode disabled: supervisord now starts at login (LaunchAgent).")


@boot_app.command("status")
def boot_status() -> None:
    """Show whether Hive starts at boot (daemon), at login (agent), or not at all."""
    from hive.shared import supervisor
    from hive.shared.supervisor import is_launchagent_installed, is_launchdaemon_installed

    if is_launchdaemon_installed():
        typer.echo(f"Mode: daemon (starts at boot) — {supervisor.LAUNCHDAEMON_PLIST}")
        result = subprocess.run(
            ["launchctl", "print", f"system/{supervisor.LAUNCHD_LABEL}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and "state = running" in result.stdout:
            typer.echo("State: running")
        else:
            typer.echo(
                "State: unknown — check with: "
                f"sudo launchctl print system/{supervisor.LAUNCHD_LABEL}"
            )
    elif is_launchagent_installed():
        typer.echo(f"Mode: agent (starts at login) — {supervisor.LAUNCHAGENT_PLIST}")
    else:
        typer.echo("Not installed. Run 'hive init <name>' or 'hive repair' first.")


comb_app = typer.Typer(help="Manage the Comb dashboard server.")
app.add_typer(comb_app, name="comb")


@comb_app.command("serve", hidden=True)
def comb_serve(
    host: str = typer.Option("127.0.0.1"),
    port: int | None = typer.Option(None),
) -> None:
    """[Internal] Comb dashboard server entrypoint."""
    from hive.comb.server import serve

    serve(host=host, port=port)


@comb_app.command("start")
def comb_start() -> None:
    """Start the Comb dashboard server."""
    from hive.shared.supervisor import reload_supervisord, supervisorctl

    reload_supervisord()
    result = supervisorctl("start", "hive-comb")
    typer.echo(result.stdout.strip() if result.stdout else "Started hive-comb")


@comb_app.command("stop")
def comb_stop() -> None:
    """Stop the Comb dashboard server."""
    from hive.shared.supervisor import supervisorctl

    result = supervisorctl("stop", "hive-comb")
    typer.echo(result.stdout.strip() if result.stdout else "Stopped hive-comb")


@comb_app.command("restart")
def comb_restart() -> None:
    """Restart the Comb dashboard server."""
    from hive.shared.supervisor import reload_supervisord, supervisorctl

    reload_supervisord()
    result = supervisorctl("restart", "hive-comb")
    typer.echo(result.stdout.strip() if result.stdout else "Restarted hive-comb")


def _write_if_missing(path: Path, content: str) -> None:
    """Write content to path only if the file doesn't already exist."""
    if not path.exists():
        path.write_text(content)


