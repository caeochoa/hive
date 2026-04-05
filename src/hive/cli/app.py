"""Hive CLI — all commands."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(name="hive", help="Hive — local-first Telegram bot framework")

HIVE_TOML_TEMPLATE = """\
[worker]
name = "{name}"

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
"""

GITIGNORE_TEMPLATE = """\
.env
.venv/
logs/
*.pyc
__pycache__/
*.tmp
.DS_Store
.streamlit/
"""

REQUIREMENTS_TEMPLATE = """\
# Add Worker-specific Python dependencies here.
# Install with: .venv/bin/pip install -r requirements.txt
"""


@app.command()
def init(name: str = typer.Argument(..., help="Name for the new Worker")) -> None:
    """Scaffold a new Worker folder. Register with supervisord. Install LaunchAgent + Comb on first use."""
    from hive.shared.registry import HiveRegistry
    from hive.shared.supervisor import (
        ensure_supervisord_conf,
        install_launchagent,
        is_launchagent_installed,
        reload_supervisord,
        write_comb_block,
        write_worker_block,
    )

    worker_dir = Path.cwd() / name
    worker_dir = worker_dir.resolve()

    # First-use setup
    if not is_launchagent_installed():
        typer.echo("First-time setup: configuring supervisord and LaunchAgent...")
        ensure_supervisord_conf()
        write_comb_block()
        try:
            install_launchagent()
        except RuntimeError as e:
            typer.echo(f"Warning: {e}", err=True)
        reload_supervisord()

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
    _write_if_missing(worker_dir / "hive.toml", HIVE_TOML_TEMPLATE.format(name=name))
    _write_if_missing(worker_dir / ".env", ENV_TEMPLATE)
    _write_if_missing(worker_dir / "requirements.txt", REQUIREMENTS_TEMPLATE)
    _write_if_missing(worker_dir / ".gitignore", GITIGNORE_TEMPLATE)

    # Register with supervisord
    write_worker_block(name, worker_dir)
    HiveRegistry().register(name, str(worker_dir))
    reload_supervisord()

    typer.echo(f"Worker '{name}' created at {worker_dir}")
    typer.echo("Edit .env to add your TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID")


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

    # Start per-worker Streamlit dashboard if [comb] is configured
    if config.comb_cells:
        from hive.shared.supervisor import write_comb_app_block
        import importlib.util
        _spec = importlib.util.find_spec("hive.comb.default_app")
        default_app_path = Path(_spec.origin).resolve()
        worker_app_path = worker_dir / "dashboard" / "app.py"
        app_path = worker_app_path if worker_app_path.exists() else default_app_path

        port = _find_free_port()
        write_comb_app_block(name, worker_dir, app_path, port)
        registry.register(name, str(worker_dir), comb_port=port)
        from hive.comb.themes import write_streamlit_theme
        write_streamlit_theme(worker_dir, config.comb_theme)
        reload_supervisord()
        comb_result = supervisorctl("start", f"comb-{name}")
        comb_msg = comb_result.stdout.strip() if comb_result.stdout else f"Started comb-{name} on port {port}"
        typer.echo(comb_msg)


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

    # Stop comb process if registered
    from hive.shared.registry import HiveRegistry as _HiveRegistry
    from hive.shared.supervisor import get_comb_app_conf_path
    _registry = _HiveRegistry()
    if _registry.get_comb_port(config.name) is not None:
        comb_result = supervisorctl("stop", f"comb-{config.name}")
        typer.echo(comb_result.stdout.strip() if comb_result.stdout else f"Stopped comb-{config.name}")


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

    # Restart comb process if registered
    from hive.shared.registry import HiveRegistry as _HiveRegistry
    _registry = _HiveRegistry()
    if _registry.get_comb_port(config.name) is not None:
        comb_result = supervisorctl("restart", f"comb-{config.name}")
        typer.echo(comb_result.stdout.strip() if comb_result.stdout else f"Restarted comb-{config.name}")


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

    # Remove comb supervisord block if it exists
    from hive.shared.supervisor import remove_comb_app_block
    remove_comb_app_block(name)

    reload_supervisord()

    typer.echo(f"Worker '{name}' unregistered")

    if delete:
        typer.confirm(f"Delete folder {worker_dir}?", abort=True)
        shutil.rmtree(worker_dir)
        typer.echo(f"Deleted {worker_dir}")


@app.command()
def status() -> None:
    """Show status of all Workers."""
    from hive.shared.supervisor import supervisorctl

    result = supervisorctl("status")
    if result.stdout:
        typer.echo(result.stdout.strip())
    else:
        typer.echo("No workers running")


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


def _find_free_port(start: int = 8501) -> int:
    """Find a free TCP port starting from start."""
    import socket
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                port += 1


def _write_if_missing(path: Path, content: str) -> None:
    """Write content to path only if the file doesn't already exist."""
    if not path.exists():
        path.write_text(content)


def is_launchagent_installed() -> bool:
    """Check if the LaunchAgent plist exists."""
    from hive.shared.supervisor import LAUNCHAGENT_PLIST

    return LAUNCHAGENT_PLIST.exists()
