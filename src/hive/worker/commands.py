"""Command discovery, parsing, and execution for Worker scripts."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any

import yaml
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from hive.shared.config import WorkerConfig
from hive.shared.models import CommandArg, CommandMeta
from hive.worker.utils import md_to_telegram_html, send_long_message, typing_action

logger = logging.getLogger(__name__)

_DOCSTRING_RE = re.compile(r'^\s*"""(.*?)"""', re.DOTALL)


class CommandError(Exception):
    """Raised when a command script exits with a non-zero status."""

    def __init__(self, stderr: str) -> None:
        self.stderr = stderr
        super().__init__(stderr)


class CommandRegistry:
    """Discovers, parses, and executes command scripts in a Worker folder."""

    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._commands: dict[str, CommandMeta] = {}

    @property
    def commands(self) -> dict[str, CommandMeta]:
        return dict(self._commands)

    def discover(self) -> None:
        """Glob commands/*.py under worker_dir, parse docstrings, skip invalid."""
        commands_dir = self._config.worker_dir / "commands"
        if not commands_dir.is_dir():
            logger.warning("No commands/ directory in %s", self._config.worker_dir)
            return

        self._commands.clear()
        for path in sorted(commands_dir.glob("*.py")):
            try:
                meta = self._parse_script(path)
                self._commands[meta.name] = meta
            except (ValueError, yaml.YAMLError) as exc:
                logger.warning("Skipping invalid command script %s: %s", path, exc)
        logger.info("Discovered %d commands: %s", len(self._commands), list(self._commands))

    def _parse_script(self, path: Path) -> CommandMeta:
        """Extract and parse the YAML docstring from a command script."""
        source = path.read_text(encoding="utf-8")
        if source.startswith("#!"):
            source = source[source.index("\n") + 1:]
        logger.debug("Parsing %s (source[:50]=%r)", path.name, source[:50])
        match = _DOCSTRING_RE.search(source)
        if not match:
            logger.warning("No docstring match in %s, source[:80]=%r", path.name, source[:80])
            raise ValueError(f"No docstring found in {path}")

        raw = yaml.safe_load(match.group(1))
        if not isinstance(raw, dict):
            raise ValueError(f"Docstring in {path} is not a YAML mapping")
        if "name" not in raw:
            raise ValueError(f"Missing 'name' in docstring of {path}")
        if "description" not in raw:
            raise ValueError(f"Missing 'description' in docstring of {path}")

        args_raw = raw.get("args", [])
        args = [CommandArg(**a) for a in args_raw]

        return CommandMeta(
            name=raw["name"],
            description=raw["description"],
            script_path=str(path.resolve()),
            args=args,
        )

    async def execute(
        self, meta: CommandMeta, args: dict[str, str | int | float | bool]
    ) -> str:
        """Run a command script as a subprocess and return its stdout."""
        venv_python = self._config.worker_dir / ".venv" / "bin" / "python"

        logger.info("Executing command %r with args %r", meta.name, args)
        cmd_args: list[str] = [str(venv_python), meta.script_path]
        for arg_def in meta.args:
            if arg_def.name not in args:
                continue
            value = args[arg_def.name]
            if arg_def.type == "bool":
                if value:
                    cmd_args.append(f"--{arg_def.name}")
            else:
                cmd_args.append(str(value))

        logger.debug("Subprocess args: %r", cmd_args)
        env = {**os.environ, "WORKER_DIR": str(self._config.worker_dir)}

        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise CommandError(stderr.decode("utf-8", errors="replace"))

        result = stdout.decode("utf-8", errors="replace")
        logger.info("Command %r returned %d chars", meta.name, len(result))
        return result

    def telegram_handlers(self) -> list[CommandHandler]:
        """Build a Telegram CommandHandler for each discovered command."""
        handlers: list[CommandHandler] = []
        for meta in self._commands.values():
            handler = self._make_handler(meta)
            handlers.append(handler)
        return handlers

    def _make_handler(self, meta: CommandMeta) -> CommandHandler:
        """Create a single Telegram CommandHandler for a CommandMeta."""

        async def callback(
            update: Update, context: ContextTypes.DEFAULT_TYPE
        ) -> None:
            user = update.effective_user
            if user is None or user.id not in self._config.telegram_allowed_user_ids:
                return

            # Parse positional args from context.args
            args: dict[str, str | int | float | bool] = {}
            telegram_args = context.args or []
            arg_defs = meta.args
            for i, arg_def in enumerate(arg_defs):
                is_last = i == len(arg_defs) - 1
                if i < len(telegram_args):
                    if is_last and arg_def.type == "str" and len(telegram_args) > i + 1:
                        args[arg_def.name] = " ".join(telegram_args[i:])
                    else:
                        args[arg_def.name] = _cast_arg(telegram_args[i], arg_def.type)
                elif arg_def.default is not None:
                    args[arg_def.name] = arg_def.default
                # If required and not provided, skip — script will error

            try:
                async with typing_action(context.bot, update.effective_chat.id):
                    result = await self.execute(meta, args)
                await send_long_message(update.message, md_to_telegram_html(result or "(no output)"), parse_mode="HTML")  # type: ignore[union-attr]
            except CommandError as exc:
                await send_long_message(update.message, f"Error: {exc.stderr}", parse_mode="HTML")  # type: ignore[union-attr]

        return CommandHandler(meta.name, callback)

    def build_input_schema(self, meta: CommandMeta) -> dict[str, Any]:
        """Build a JSON Schema dict from a CommandMeta's args."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg in meta.args:
            type_map = {"int": "integer", "float": "number", "bool": "boolean"}
            prop: dict[str, Any] = {"type": type_map.get(arg.type, "string")}
            prop["description"] = arg.description
            properties[arg.name] = prop
            if arg.required:
                required.append(arg.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def build_mcp_tools(self) -> list[Any] | None:
        """Build the list of MCP tools for all discovered commands."""
        if not self._commands:
            return None

        from claude_agent_sdk import SdkMcpTool

        tools: list[Any] = []
        for meta in self._commands.values():
            input_schema = self.build_input_schema(meta)

            async def handler(
                args: dict[str, Any], meta: CommandMeta = meta
            ) -> dict[str, Any]:
                # Fill in defaults for optional args not provided
                filled: dict[str, str | int | float | bool] = {}
                for arg_def in meta.args:
                    if arg_def.name in args:
                        filled[arg_def.name] = args[arg_def.name]
                    elif arg_def.default is not None:
                        filled[arg_def.name] = arg_def.default
                try:
                    result = await self.execute(meta, filled)
                    return {"content": [{"type": "text", "text": result}]}
                except CommandError as exc:
                    return {
                        "content": [{"type": "text", "text": f"Error: {exc.stderr}"}],
                        "is_error": True,
                    }

            tools.append(
                SdkMcpTool(
                    name=meta.name,
                    description=meta.description,
                    input_schema=input_schema,
                    handler=handler,
                )
            )

        return tools

    def build_mcp_server(self) -> Any:
        """Build an in-process MCP server exposing all discovered commands as tools."""
        tools = self.build_mcp_tools()
        if tools is None:
            return None

        from claude_agent_sdk import create_sdk_mcp_server

        return create_sdk_mcp_server("commands", tools=tools)


def _cast_arg(value: str, type_name: str) -> str | int | float | bool:
    """Cast a string argument to the declared type."""
    match type_name:
        case "int":
            return int(value)
        case "float":
            return float(value)
        case "bool":
            return value.lower() in ("true", "1", "yes")
        case _:
            return value
