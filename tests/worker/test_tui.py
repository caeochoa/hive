"""Tests for hive.worker.tui module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.shared.config import WorkerConfig
from hive.shared.models import CommandArg, CommandMeta
from hive.worker.commands import CommandError
from hive.worker.tui import (
    TUI_CHAT_ID,
    _auto_commit,
    _detect_changes,
    _dispatch_worker_command,
    _looks_like_markdown,
    _tui_help,
    _tui_menu,
    _tui_reset,
    _tui_set,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_session(
    commands: dict[str, CommandMeta] | None = None,
) -> MagicMock:
    """Build a minimal _TuiSession-like mock."""
    session = MagicMock()
    session.agent = MagicMock()
    session.agent.reset_session = AsyncMock()
    session.agent.set_session_override = MagicMock()
    session.agent.clear_session_override = MagicMock()
    session.registry = MagicMock()
    session.registry.commands = commands or {}
    session.registry.execute = AsyncMock(return_value="ok")
    session.config = MagicMock()
    session.console = MagicMock()
    return session


_GREET_META = CommandMeta(
    name="greet",
    description="Say hello",
    script_path="/fake/greet.py",
    args=[CommandArg(name="who", type="str", description="Name", default="world")],
)

_REQUIRED_META = CommandMeta(
    name="deploy",
    description="Deploy",
    script_path="/fake/deploy.py",
    args=[CommandArg(name="target", type="str", description="Target")],
)


# ---------------------------------------------------------------------------
# _tui_reset
# ---------------------------------------------------------------------------


class TestTuiReset:
    async def test_calls_reset_and_returns_message(self) -> None:
        session = _make_session()
        result = await _tui_reset(session, "")
        session.agent.reset_session.assert_awaited_once_with(TUI_CHAT_ID)
        assert result == "Session reset."


# ---------------------------------------------------------------------------
# _tui_help
# ---------------------------------------------------------------------------


class TestTuiHelp:
    async def test_contains_builtin_commands(self) -> None:
        session = _make_session()
        result = await _tui_help(session, "")
        assert "/reset" in result
        assert "/help" in result
        assert "/menu" in result
        assert "/set" in result
        assert "/exit" in result

    async def test_includes_worker_commands(self) -> None:
        session = _make_session({"greet": _GREET_META})
        result = await _tui_help(session, "")
        assert "Worker commands:" in result
        assert "/greet" in result
        assert "Say hello" in result

    async def test_no_worker_commands(self) -> None:
        session = _make_session()
        result = await _tui_help(session, "")
        assert "No worker commands" in result


# ---------------------------------------------------------------------------
# _tui_set
# ---------------------------------------------------------------------------


class TestTuiSet:
    async def test_empty_args_returns_usage(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "")
        assert "Usage" in result

    async def test_reset_clears_overrides(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "reset")
        session.agent.clear_session_override.assert_called_once_with(TUI_CHAT_ID)
        assert "cleared" in result.lower()

    async def test_valid_model_accepted(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "model claude-opus-4-6")
        session.agent.set_session_override.assert_called_once_with(
            TUI_CHAT_ID, model="claude-opus-4-6"
        )
        assert "updated" in result.lower()

    async def test_invalid_model_rejected(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "model gpt-4")
        session.agent.set_session_override.assert_not_called()
        assert "Invalid model" in result

    async def test_int_key_parsed(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "max_turns 20")
        session.agent.set_session_override.assert_called_once_with(
            TUI_CHAT_ID, max_turns=20
        )
        assert "updated" in result.lower()

    async def test_int_key_rejects_non_int(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "max_turns abc")
        session.agent.set_session_override.assert_not_called()
        assert "integer" in result.lower()

    async def test_unknown_key_rejected(self) -> None:
        session = _make_session()
        result = await _tui_set(session, "temperature 0.5")
        assert "Unknown setting" in result


# ---------------------------------------------------------------------------
# _tui_menu
# ---------------------------------------------------------------------------


class TestTuiMenu:
    async def test_lists_commands(self) -> None:
        session = _make_session({"greet": _GREET_META})
        result = await _tui_menu(session, "")
        assert "/greet" in result

    async def test_empty_when_no_commands(self) -> None:
        session = _make_session()
        result = await _tui_menu(session, "")
        assert "No worker commands" in result


# ---------------------------------------------------------------------------
# _dispatch_worker_command
# ---------------------------------------------------------------------------


class TestDispatchWorkerCommand:
    async def test_unknown_command_returns_error(self) -> None:
        session = _make_session()
        result = await _dispatch_worker_command(session, "nope", "")
        assert "Unknown command" in result

    async def test_valid_command_calls_execute(self) -> None:
        session = _make_session({"greet": _GREET_META})
        result = await _dispatch_worker_command(session, "greet", "Alice")
        session.registry.execute.assert_awaited_once()
        assert result == "ok"

    async def test_command_error_surfaces_stdout_and_stderr(self) -> None:
        session = _make_session({"greet": _GREET_META})
        session.registry.execute = AsyncMock(
            side_effect=CommandError("fail", stdout="partial")
        )
        with pytest.raises(CommandError) as exc_info:
            await _dispatch_worker_command(session, "greet", "")
        assert exc_info.value.stdout == "partial"
        assert exc_info.value.stderr == "fail"


# ---------------------------------------------------------------------------
# _looks_like_markdown
# ---------------------------------------------------------------------------


class TestLooksLikeMarkdown:
    @pytest.mark.parametrize(
        "text",
        [
            "# Heading",
            "```code```",
            "**bold**",
            "- item",
            "* item",
            "1. item",
        ],
    )
    def test_returns_true_for_markdown(self, text: str) -> None:
        assert _looks_like_markdown(text) is True

    @pytest.mark.parametrize("text", ["hello world", "just plain text", "no markers"])
    def test_returns_false_for_plain(self, text: str) -> None:
        assert _looks_like_markdown(text) is False


# ---------------------------------------------------------------------------
# _detect_changes
# ---------------------------------------------------------------------------


class TestDetectChanges:
    def test_no_change_returns_false(self) -> None:
        snap = {Path("a"): 100}
        assert _detect_changes(snap, snap) is False

    def test_mtime_changed_returns_true(self) -> None:
        assert _detect_changes({Path("a"): 100}, {Path("a"): 200}) is True

    def test_new_file_returns_true(self) -> None:
        assert _detect_changes({}, {Path("a"): 100}) is True

    def test_deleted_file_returns_true(self) -> None:
        assert _detect_changes({Path("a"): 100}, {}) is True

    def test_identical_returns_false(self) -> None:
        snap = {Path("a"): 1, Path("b"): 2}
        assert _detect_changes(snap, snap.copy()) is False


# ---------------------------------------------------------------------------
# _auto_commit
# ---------------------------------------------------------------------------


class TestAutoCommit:
    async def test_calls_git_add_diff_commit(self, tmp_path: Path) -> None:
        calls: list[tuple] = []

        async def fake_subprocess(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            if "diff" in args:
                proc.returncode = 1  # staged changes exist
            else:
                proc.returncode = 0
            return proc

        with patch(
            "hive.worker.tui.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            await _auto_commit(tmp_path)

        assert len(calls) == 3
        assert calls[0][0] == "git" and calls[0][1] == "add"
        assert calls[1][0] == "git" and calls[1][1] == "diff"
        assert calls[2][0] == "git" and calls[2][1] == "commit"

    async def test_skips_commit_when_nothing_staged(self, tmp_path: Path) -> None:
        calls: list[tuple] = []

        async def fake_subprocess(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0  # diff --cached --quiet: nothing staged
            return proc

        with patch(
            "hive.worker.tui.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            await _auto_commit(tmp_path)

        # Only git add + git diff, no commit
        assert len(calls) == 2
