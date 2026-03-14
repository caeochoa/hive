"""Tests for hive.worker.commands module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.shared.config import WorkerConfig
from hive.shared.models import CommandArg, CommandMeta
from hive.worker.commands import CommandError, CommandRegistry, _cast_arg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SCRIPT = '''\
"""
name: greet
description: Say hello
args:
  - name: who
    type: str
    description: Name to greet
    default: world
"""
import sys
print(f"Hello, {sys.argv[2]}!")
'''

INVALID_SCRIPT_NO_DOCSTRING = """\
# no docstring here
print("hi")
"""

INVALID_SCRIPT_MISSING_NAME = '''\
"""
description: Missing name field
"""
print("hi")
'''


@pytest.fixture
def worker_dir(tmp_path: Path) -> Path:
    """Set up a minimal worker directory with command scripts."""
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    (commands_dir / "greet.py").write_text(VALID_SCRIPT)
    (commands_dir / "broken.py").write_text(INVALID_SCRIPT_NO_DOCSTRING)
    (commands_dir / "bad_meta.py").write_text(INVALID_SCRIPT_MISSING_NAME)

    # Create .venv/bin/python placeholder
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").touch()

    return tmp_path


@pytest.fixture
def config(worker_dir: Path) -> WorkerConfig:
    return WorkerConfig(
        name="test-worker",
        worker_dir=worker_dir,
        telegram_bot_token="fake-token",
        telegram_allowed_user_id=12345,
    )


@pytest.fixture
def registry(config: WorkerConfig) -> CommandRegistry:
    return CommandRegistry(config)


# ---------------------------------------------------------------------------
# _parse_script
# ---------------------------------------------------------------------------


class TestParseScript:
    def test_valid_script(self, registry: CommandRegistry, worker_dir: Path) -> None:
        meta = registry._parse_script(worker_dir / "commands" / "greet.py")
        assert meta.name == "greet"
        assert meta.description == "Say hello"
        assert len(meta.args) == 1
        assert meta.args[0].name == "who"
        assert meta.args[0].type == "str"
        assert meta.args[0].default == "world"
        assert Path(meta.script_path).is_absolute()

    def test_no_docstring_raises(
        self, registry: CommandRegistry, worker_dir: Path
    ) -> None:
        with pytest.raises(ValueError, match="No docstring found"):
            registry._parse_script(worker_dir / "commands" / "broken.py")

    def test_missing_name_raises(
        self, registry: CommandRegistry, worker_dir: Path
    ) -> None:
        with pytest.raises(ValueError, match="Missing 'name'"):
            registry._parse_script(worker_dir / "commands" / "bad_meta.py")


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


class TestDiscover:
    def test_discovers_valid_commands(self, registry: CommandRegistry) -> None:
        registry.discover()
        cmds = registry.commands
        assert "greet" in cmds
        assert len(cmds) == 1  # broken + bad_meta skipped

    def test_skips_invalid_scripts(self, registry: CommandRegistry) -> None:
        registry.discover()
        cmds = registry.commands
        assert "broken" not in cmds
        assert "bad_meta" not in cmds

    def test_no_commands_dir(self, tmp_path: Path) -> None:
        config = WorkerConfig(
            name="empty",
            worker_dir=tmp_path,
            telegram_bot_token="fake",
            telegram_allowed_user_id=1,
        )
        reg = CommandRegistry(config)
        reg.discover()
        assert reg.commands == {}


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class TestExecute:
    async def test_execute_success(self, registry: CommandRegistry) -> None:
        meta = CommandMeta(
            name="test",
            description="test cmd",
            script_path="/fake/script.py",
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"output line\n", b"")
        mock_proc.returncode = 0

        with patch("hive.worker.commands.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await registry.execute(meta, {"key": "value"})

        assert result == "output line\n"
        # Verify the command was constructed correctly
        call_args = mock_exec.call_args
        positional = call_args[0]
        assert positional[-1] == "value"
        assert positional[-2] == "--key"
        assert "WORKER_DIR" in call_args[1]["env"]

    async def test_execute_nonzero_raises_command_error(
        self, registry: CommandRegistry
    ) -> None:
        meta = CommandMeta(
            name="fail",
            description="fails",
            script_path="/fake/fail.py",
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"something went wrong\n")
        mock_proc.returncode = 1

        with patch("hive.worker.commands.asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(CommandError) as exc_info:
                await registry.execute(meta, {})

        assert "something went wrong" in exc_info.value.stderr

    async def test_execute_passes_worker_dir_env(
        self, registry: CommandRegistry, config: WorkerConfig
    ) -> None:
        meta = CommandMeta(
            name="env_test", description="test", script_path="/fake/s.py"
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"ok", b"")
        mock_proc.returncode = 0

        with patch("hive.worker.commands.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await registry.execute(meta, {})

        env = mock_exec.call_args[1]["env"]
        assert env["WORKER_DIR"] == str(config.worker_dir)


# ---------------------------------------------------------------------------
# telegram_handlers
# ---------------------------------------------------------------------------


class TestTelegramHandlers:
    def test_returns_handler_per_command(self, registry: CommandRegistry) -> None:
        registry.discover()
        handlers = registry.telegram_handlers()
        assert len(handlers) == 1
        # The handler should be for the "greet" command
        assert "greet" in handlers[0].commands

    def test_no_handlers_when_no_commands(self, registry: CommandRegistry) -> None:
        # Don't call discover
        handlers = registry.telegram_handlers()
        assert handlers == []


# ---------------------------------------------------------------------------
# build_mcp_server
# ---------------------------------------------------------------------------


class TestBuildMcpServer:
    def test_returns_none_stub(self, registry: CommandRegistry) -> None:
        assert registry.build_mcp_server() is None


# ---------------------------------------------------------------------------
# CommandError
# ---------------------------------------------------------------------------


class TestCommandError:
    def test_stderr_attribute(self) -> None:
        err = CommandError("bad stuff")
        assert err.stderr == "bad stuff"
        assert str(err) == "bad stuff"


# ---------------------------------------------------------------------------
# _cast_arg helper
# ---------------------------------------------------------------------------


class TestCastArg:
    def test_int(self) -> None:
        assert _cast_arg("42", "int") == 42

    def test_float(self) -> None:
        assert _cast_arg("3.14", "float") == pytest.approx(3.14)

    def test_bool_true(self) -> None:
        assert _cast_arg("true", "bool") is True

    def test_bool_false(self) -> None:
        assert _cast_arg("no", "bool") is False

    def test_str(self) -> None:
        assert _cast_arg("hello", "str") == "hello"
