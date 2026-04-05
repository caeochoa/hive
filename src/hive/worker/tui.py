"""TUI chat session for hive chat <path>."""

from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rich.console import Console
from rich.markdown import Markdown

from hive.shared.config import WorkerConfig
from hive.worker.agent import DEFAULT_SYSTEM_PROMPT, ClaudeAgentRunner
from hive.worker.builtin_tools import build_builtin_mcp_server
from hive.worker.builtins import VALID_INT_KEYS, VALID_KEYS, validate_model_id
from hive.worker.commands import CommandError, CommandRegistry

logger = logging.getLogger(__name__)

TUI_CHAT_ID = 0  # Virtual chat ID; gives TUI its own session slot.


@dataclass
class _TuiSession:
    # Typed as ClaudeAgentRunner (not AgentRunner) because the TUI needs
    # session override methods that only exist on the concrete class.
    agent: ClaudeAgentRunner
    registry: CommandRegistry
    config: WorkerConfig
    console: Console


def _build_system_prompt(config: WorkerConfig) -> str:
    if config.agent_system_prompt:
        return config.agent_system_prompt
    return DEFAULT_SYSTEM_PROMPT


def build_tui_session(config: WorkerConfig) -> _TuiSession:
    registry = CommandRegistry(config)
    registry.discover()
    commands_mcp = registry.build_mcp_server()
    command_names = list(registry._commands) if commands_mcp is not None else []

    agent_config = SimpleNamespace(
        model=config.agent_model,
        system_prompt=_build_system_prompt(config),
        max_turns=config.agent_max_turns,
        memory_dir=config.agent_memory_dir,
        thinking_budget_tokens=config.agent_thinking_budget_tokens,
    )
    sessions_file = config.worker_dir / config.agent_memory_dir / ".sessions.json"
    agent = ClaudeAgentRunner(
        agent_config, commands_mcp, command_names, sessions_file, config.worker_dir
    )
    agent.set_builtins_mcp(build_builtin_mcp_server(agent))

    return _TuiSession(
        agent=agent,
        registry=registry,
        config=config,
        console=Console(),
    )


# ------------------------------------------------------------------ #
# Built-in TUI handlers
# ------------------------------------------------------------------ #

async def _tui_reset(session: _TuiSession, args_str: str) -> str:
    await session.agent.reset_session(TUI_CHAT_ID)
    return "Session reset."


async def _tui_help(session: _TuiSession, args_str: str) -> str:
    lines = [
        "Built-in commands:",
        "  /reset              — Start a fresh conversation",
        "  /help               — Show this message",
        "  /menu               — List worker commands",
        "  /set <key> <value>  — Override session config (model, max_turns, thinking_budget_tokens)",
        "  /set reset          — Clear all session overrides",
        "  /exit, /quit        — Exit hive chat",
        "",
    ]
    if session.registry.commands:
        lines.append("Worker commands:")
        for meta in session.registry.commands.values():
            arg_parts = []
            for a in meta.args:
                if a.required:
                    arg_parts.append(f"<{a.name}>")
                else:
                    arg_parts.append(f"[{a.name}={a.default}]")
            arg_hint = (" " + " ".join(arg_parts)) if arg_parts else ""
            lines.append(f"  /{meta.name}{arg_hint} — {meta.description}")
    else:
        lines.append("No worker commands discovered.")
    return "\n".join(lines)


async def _tui_set(session: _TuiSession, args_str: str) -> str:
    args_str = args_str.strip()
    if not args_str:
        return (
            "Usage:\n"
            "  /set model <model-id>          e.g. claude-opus-4-6\n"
            "  /set max_turns <n>\n"
            "  /set thinking_budget_tokens <n>\n"
            "  /set reset                     clear all overrides"
        )

    if args_str == "reset":
        session.agent.clear_session_override(TUI_CHAT_ID)
        return "Session overrides cleared. Using config defaults."

    tokens = args_str.split(maxsplit=1)
    if len(tokens) != 2:
        return "Usage: /set <key> <value>  or  /set reset"

    key, value = tokens
    if key not in VALID_KEYS:
        valid = ", ".join(sorted(VALID_KEYS))
        return f"Unknown setting '{key}'. Valid settings: {valid}"

    if key in VALID_INT_KEYS:
        try:
            parsed_value: Any = int(value)
        except ValueError:
            return f"'{key}' must be an integer."
    else:
        parsed_value = value
        if key == "model":
            err = validate_model_id(value)
            if err:
                return err

    session.agent.set_session_override(TUI_CHAT_ID, **{key: parsed_value})
    return f"Session config updated: {key}={parsed_value}. Takes effect from the next message."


async def _tui_menu(session: _TuiSession, args_str: str) -> str:
    if not session.registry.commands:
        return "No worker commands available."
    lines = ["Worker commands:"]
    for meta in session.registry.commands.values():
        parts = [f"/{meta.name}"]
        for a in meta.args:
            parts.append(f"[{a.name}={a.default}]" if not a.required else f"<{a.name}>")
        lines.append("  " + " ".join(parts) + f"  — {meta.description}")
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Command dispatch
# ------------------------------------------------------------------ #

async def _dispatch_worker_command(session: _TuiSession, name: str, args_str: str) -> str:
    meta = session.registry.commands.get(name)
    if meta is None:
        return f"Unknown command: /{name}. Use /help."

    raw_args = shlex.split(args_str) if args_str.strip() else []
    args: dict[str, Any] = {}
    for i, arg_def in enumerate(meta.args):
        if i < len(raw_args):
            from hive.worker.commands import cast_arg
            args[arg_def.name] = cast_arg(raw_args[i], arg_def.type)
        elif arg_def.default is not None:
            args[arg_def.name] = arg_def.default

    result = await session.registry.execute(meta, args)
    return result or "(no output)"


# ------------------------------------------------------------------ #
# Rendering
# ------------------------------------------------------------------ #

def _looks_like_markdown(text: str) -> bool:
    return any(marker in text for marker in ("#", "```", "**", "- ", "* ", "1. "))


def _print_response(console: Console, text: str) -> None:
    if _looks_like_markdown(text):
        console.print(Markdown(text))
    else:
        console.print(text)


# ------------------------------------------------------------------ #
# Auto-commit
# ------------------------------------------------------------------ #

async def _auto_commit(worker_dir: Path) -> None:
    """Git add + commit tracked paths. Skip if nothing to commit."""
    proc = await asyncio.create_subprocess_exec(
        "git", "add", "commands/", "memory/", "hive.toml", "dashboard/",
        cwd=str(worker_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    proc = await asyncio.create_subprocess_exec(
        "git", "diff", "--cached", "--quiet",
        cwd=str(worker_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode == 0:
        return

    proc = await asyncio.create_subprocess_exec(
        "git", "commit", "-m", "hive: auto-commit after agent turn",
        cwd=str(worker_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


# ------------------------------------------------------------------ #
# Config change detection
# ------------------------------------------------------------------ #

def _snapshot_paths(worker_dir: Path) -> dict[Path, int]:
    paths: dict[Path, int] = {}
    toml = worker_dir / "hive.toml"
    if toml.exists():
        paths[toml] = toml.stat().st_mtime_ns
    commands_dir = worker_dir / "commands"
    if commands_dir.is_dir():
        for p in commands_dir.glob("*.py"):
            paths[p] = p.stat().st_mtime_ns
    return paths


def _detect_changes(before: dict[Path, int], after: dict[Path, int]) -> bool:
    if set(before) != set(after):
        return True
    return any(before[p] != after[p] for p in before)


# ------------------------------------------------------------------ #
# Main REPL loop
# ------------------------------------------------------------------ #

_BUILTINS = {
    "reset": _tui_reset,
    "help": _tui_help,
    "set": _tui_set,
    "menu": _tui_menu,
}


async def _run_tui_loop(session: _TuiSession) -> None:
    console = session.console
    config = session.config

    console.print(f"[bold]hive chat[/bold] — [cyan]{config.name}[/cyan]")
    console.print("[dim]Type a message or /command. Ctrl-C or /exit to quit.[/dim]")
    console.print()

    loop = asyncio.get_running_loop()

    while True:
        try:
            line: str = await loop.run_in_executor(None, input, "> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        line = line.strip()
        if not line:
            continue

        if line in ("/exit", "/quit"):
            console.print("[dim]Goodbye.[/dim]")
            break

        if line.startswith("/"):
            # Split off command name and rest
            rest = line[1:]
            parts = rest.split(maxsplit=1)
            name = parts[0]
            args_str = parts[1] if len(parts) > 1 else ""

            if name in _BUILTINS:
                result = await _BUILTINS[name](session, args_str)
                console.print(result)
            else:
                try:
                    result = await _dispatch_worker_command(session, name, args_str)
                    _print_response(console, result)
                except CommandError as exc:
                    if exc.stdout.strip():
                        console.print(exc.stdout.strip())
                    console.print(f"[red]Error:[/red] {exc.stderr.strip()}")
        else:
            before = _snapshot_paths(config.worker_dir)
            try:
                with console.status("[dim]Thinking...[/dim]"):
                    response = await session.agent.run(line, TUI_CHAT_ID, config.worker_dir)
                _print_response(console, response)
                after = _snapshot_paths(config.worker_dir)
                if _detect_changes(before, after):
                    console.print(
                        "[yellow]Worker config files changed.[/yellow] "
                        "Run [bold]hive restart <path>[/bold] to apply changes."
                    )
            except Exception as exc:
                logger.debug("Agent error traceback", exc_info=True)
                console.print(f"[red]Agent error:[/red] {exc}")

        await _auto_commit(config.worker_dir)


async def run_tui(config: WorkerConfig) -> None:
    session = build_tui_session(config)
    try:
        await _run_tui_loop(session)
    finally:
        await session.agent.close()
