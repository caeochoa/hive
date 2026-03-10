import typer

app = typer.Typer(name="hive", help="Local-first Telegram bot framework")


@app.command()
def init(name: str = typer.Argument(..., help="Worker name")) -> None:
    """Scaffold a new Worker folder and register it."""
    typer.echo(f"[stub] hive init {name}")


@app.command()
def start(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Start a Worker process."""
    typer.echo(f"[stub] hive start {path}")


@app.command()
def stop(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Stop a Worker process."""
    typer.echo(f"[stub] hive stop {path}")


@app.command()
def restart(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """Restart a Worker process."""
    typer.echo(f"[stub] hive restart {path}")


@app.command()
def remove(
    path: str = typer.Argument(..., help="Path to Worker folder"),
    delete: bool = typer.Option(False, "--delete", help="Also delete the folder"),
) -> None:
    """Unregister and stop a Worker."""
    typer.echo(f"[stub] hive remove {path}")


@app.command()
def status() -> None:
    """Show status of all Workers."""
    typer.echo("[stub] hive status")


@app.command()
def logs(
    path: str = typer.Argument(..., help="Path to Worker folder"),
    lines: int = typer.Option(50, "-n", help="Number of lines"),
    follow: bool = typer.Option(False, "-f", help="Follow log"),
) -> None:
    """Tail Worker logs."""
    typer.echo(f"[stub] hive logs {path}")


@app.command()
def run(path: str = typer.Argument(..., help="Path to Worker folder")) -> None:
    """[Internal] Worker entrypoint called by supervisord."""
    typer.echo(f"[stub] hive run {path}")


@app.command()
def comb() -> None:
    """[Internal] Comb dashboard server entrypoint."""
    typer.echo("[stub] hive comb")
