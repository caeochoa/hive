"""Tests for hive.worker.runtime.WorkerRuntime."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.shared.config import load_worker_config
from hive.worker.runtime import WorkerRuntime


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def make_config(tmp_path: Path):
    (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\n')
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=42\n"
    )
    return load_worker_config(tmp_path)


def _make_runtime(tmp_path: Path) -> WorkerRuntime:
    config = make_config(tmp_path)
    return WorkerRuntime(config)


# ------------------------------------------------------------------ #
# _is_allowed
# ------------------------------------------------------------------ #


class TestIsAllowed:
    def test_matching_user_returns_true(self, tmp_path):
        rt = _make_runtime(tmp_path)
        update = MagicMock()
        update.effective_user.id = 42
        assert rt._is_allowed(update) is True

    def test_wrong_user_returns_false(self, tmp_path):
        rt = _make_runtime(tmp_path)
        update = MagicMock()
        update.effective_user.id = 99
        assert rt._is_allowed(update) is False

    def test_no_user_returns_false(self, tmp_path):
        rt = _make_runtime(tmp_path)
        update = MagicMock()
        update.effective_user = None
        assert rt._is_allowed(update) is False


# ------------------------------------------------------------------ #
# _auto_commit
# ------------------------------------------------------------------ #


class TestAutoCommit:
    @pytest.mark.asyncio
    async def test_calls_git_add_diff_commit(self, tmp_path):
        rt = _make_runtime(tmp_path)
        calls = []

        async def fake_subprocess(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            # git diff --cached --quiet returns 1 when there are staged changes
            if "diff" in args:
                proc.returncode = 1
            else:
                proc.returncode = 0
            return proc

        with patch("hive.worker.runtime.asyncio.create_subprocess_exec", side_effect=fake_subprocess):
            await rt._auto_commit("test reason")

        assert len(calls) == 3

        # First call: git add
        assert calls[0][0] == "git"
        assert calls[0][1] == "add"
        assert "commands/" in calls[0]
        assert "memory/" in calls[0]

        # Second call: git diff --cached --quiet
        assert calls[1][0] == "git"
        assert calls[1][1] == "diff"
        assert "--cached" in calls[1]
        assert "--quiet" in calls[1]

        # Third call: git commit
        assert calls[2][0] == "git"
        assert calls[2][1] == "commit"
        assert "-m" in calls[2]

        # All calls should use the worker_dir as cwd
        for call_args in calls:
            # kwargs are not in the positional args, check via side_effect capture
            pass

    @pytest.mark.asyncio
    async def test_skips_commit_when_nothing_staged(self, tmp_path):
        rt = _make_runtime(tmp_path)
        calls = []

        async def fake_subprocess(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            # git diff --cached --quiet returns 0 = nothing staged
            proc.returncode = 0
            return proc

        with patch("hive.worker.runtime.asyncio.create_subprocess_exec", side_effect=fake_subprocess):
            await rt._auto_commit("test reason")

        # Only git add + git diff, no commit
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_auto_commit_uses_correct_cwd(self, tmp_path):
        rt = _make_runtime(tmp_path)
        captured_kwargs = []

        async def fake_subprocess(*args, **kwargs):
            captured_kwargs.append(kwargs)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("hive.worker.runtime.asyncio.create_subprocess_exec", side_effect=fake_subprocess):
            await rt._auto_commit("test")

        for kw in captured_kwargs:
            assert kw["cwd"] == str(tmp_path)


# ------------------------------------------------------------------ #
# _register_handlers
# ------------------------------------------------------------------ #


class TestRegisterHandlers:
    def test_registers_correct_handler_count(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = MagicMock()
        rt._app = MagicMock()
        rt._app.add_handler = MagicMock()

        # Create fake user command handlers
        fake_handler_1 = MagicMock()
        fake_handler_1.commands = frozenset({"foo"})
        fake_handler_2 = MagicMock()
        fake_handler_2.commands = frozenset({"bar"})

        rt._registry = MagicMock()
        rt._registry.telegram_handlers.return_value = [fake_handler_1, fake_handler_2]
        rt._registry.commands = {"foo": MagicMock(), "bar": MagicMock()}

        rt._register_handlers()

        # 2 built-ins + 2 user commands + 1 catch-all NL handler = 5
        assert rt._app.add_handler.call_count == 5

    def test_skips_colliding_commands(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = MagicMock()
        rt._app = MagicMock()
        rt._app.add_handler = MagicMock()

        # One handler collides with built-in "reset"
        colliding = MagicMock()
        colliding.commands = frozenset({"reset"})
        normal = MagicMock()
        normal.commands = frozenset({"foo"})

        rt._registry = MagicMock()
        rt._registry.telegram_handlers.return_value = [colliding, normal]

        rt._register_handlers()

        # 2 built-ins + 1 user command (colliding skipped) + 1 catch-all = 4
        assert rt._app.add_handler.call_count == 4


# ------------------------------------------------------------------ #
# _handle_nl_message
# ------------------------------------------------------------------ #


class TestHandleNlMessage:
    @pytest.mark.asyncio
    async def test_routes_to_agent_and_replies(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = AsyncMock()
        rt._agent.run = AsyncMock(return_value="Agent says hi")

        update = MagicMock()
        update.effective_user.id = 42
        update.effective_chat.id = 100
        update.message.text = "hello"
        update.message.reply_text = AsyncMock()

        with patch("hive.worker.runtime.send_long_message", new_callable=AsyncMock) as mock_send:
            with patch.object(rt, "_auto_commit", new_callable=AsyncMock) as mock_commit:
                await rt._handle_nl_message(update, MagicMock())

        rt._agent.run.assert_awaited_once_with("hello", 100, tmp_path)
        mock_send.assert_awaited_once_with(update.message, "Agent says hi")
        mock_commit.assert_awaited_once_with("agent turn")

    @pytest.mark.asyncio
    async def test_rejects_unauthorized_user(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = AsyncMock()

        update = MagicMock()
        update.effective_user.id = 99  # not allowed
        update.message.reply_text = AsyncMock()

        with patch.object(rt, "_auto_commit", new_callable=AsyncMock) as mock_commit:
            await rt._handle_nl_message(update, MagicMock())

        rt._agent.run.assert_not_awaited()
        # Early return means no auto-commit either
        mock_commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_agent_error_gracefully(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = AsyncMock()
        rt._agent.run = AsyncMock(side_effect=RuntimeError("boom"))

        update = MagicMock()
        update.effective_user.id = 42
        update.effective_chat.id = 100
        update.message.text = "hello"
        update.message.reply_text = AsyncMock()

        with patch.object(rt, "_auto_commit", new_callable=AsyncMock):
            await rt._handle_nl_message(update, MagicMock())

        update.message.reply_text.assert_awaited_once_with(
            "Something went wrong. Check the logs."
        )
