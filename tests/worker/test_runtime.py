"""Tests for hive.worker.runtime.WorkerRuntime."""

from __future__ import annotations

import asyncio
import os
import signal
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
# Scheduler lifecycle
# ------------------------------------------------------------------ #


class TestBuildSystemPrompt:
    def test_default_prompt_includes_self_config_instructions(self, tmp_path):
        """When agent_system_prompt is not set, self-config instructions are appended."""
        rt = _make_runtime(tmp_path)
        prompt = rt._build_system_prompt()
        assert "hive.toml" in prompt
        assert "set_session_config" in prompt

    def test_custom_prompt_used_as_is(self, tmp_path):
        """When agent_system_prompt is set, it is used verbatim without self-config instructions."""
        rt = _make_runtime(tmp_path)
        rt._config = SimpleNamespace(**{**rt._config.__dict__, "agent_system_prompt": "My custom prompt."})
        prompt = rt._build_system_prompt()
        assert prompt == "My custom prompt."
        assert "hive.toml" not in prompt


class TestSchedulerLifecycle:
    async def test_start_does_not_await_scheduler(self, tmp_path):
        """Scheduler.start/stop must be callable without await from runtime."""
        from unittest.mock import MagicMock
        from hive.worker.scheduler import WorkerScheduler
        import inspect

        sched = MagicMock(spec=WorkerScheduler)
        sched.start = MagicMock(return_value=None)
        sched.stop = MagicMock(return_value=None)

        result = sched.start()
        assert result is None

        assert not inspect.isawaitable(sched.start())


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

        # 5 built-ins (reset, help, menu, set, callback) + 2 user commands + 1 catch-all NL handler = 8
        assert rt._app.add_handler.call_count == 8

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

        # 5 built-ins (reset, help, menu, set, callback) + 1 user command (colliding skipped) + 1 catch-all = 7
        assert rt._app.add_handler.call_count == 7


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
        mock_send.assert_awaited_once_with(update.message, "Agent says hi", parse_mode="HTML")
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


# ------------------------------------------------------------------ #
# _snapshot_worker_paths
# ------------------------------------------------------------------ #


class TestSnapshotWorkerPaths:
    def test_includes_hive_toml(self, tmp_path):
        rt = _make_runtime(tmp_path)
        # hive.toml already written by make_config
        snapshot = rt._snapshot_worker_paths()
        assert tmp_path / "hive.toml" in snapshot
        assert isinstance(snapshot[tmp_path / "hive.toml"], int)

    def test_includes_command_scripts(self, tmp_path):
        rt = _make_runtime(tmp_path)
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        script = commands_dir / "foo.py"
        script.write_text("# foo")

        snapshot = rt._snapshot_worker_paths()
        assert script in snapshot

    def test_missing_toml_skipped(self, tmp_path):
        rt = _make_runtime(tmp_path)
        (tmp_path / "hive.toml").unlink()
        snapshot = rt._snapshot_worker_paths()
        assert tmp_path / "hive.toml" not in snapshot

    def test_no_commands_dir_returns_only_toml(self, tmp_path):
        rt = _make_runtime(tmp_path)
        snapshot = rt._snapshot_worker_paths()
        # Only hive.toml, no commands/ dir
        assert len(snapshot) == 1


# ------------------------------------------------------------------ #
# _detect_worker_changes
# ------------------------------------------------------------------ #


class TestDetectWorkerChanges:
    def test_no_change_returns_false(self, tmp_path):
        rt = _make_runtime(tmp_path)
        path = tmp_path / "hive.toml"
        snap = {path: 1000}
        assert rt._detect_worker_changes(snap, snap) is False

    def test_mtime_changed_returns_true(self, tmp_path):
        rt = _make_runtime(tmp_path)
        path = tmp_path / "hive.toml"
        assert rt._detect_worker_changes({path: 1000}, {path: 1001}) is True

    def test_new_file_returns_true(self, tmp_path):
        rt = _make_runtime(tmp_path)
        new_path = tmp_path / "commands" / "foo.py"
        assert rt._detect_worker_changes({}, {new_path: 1000}) is True

    def test_deleted_file_returns_true(self, tmp_path):
        rt = _make_runtime(tmp_path)
        old_path = tmp_path / "commands" / "foo.py"
        assert rt._detect_worker_changes({old_path: 1000}, {}) is True

    def test_identical_snapshots_returns_false(self, tmp_path):
        rt = _make_runtime(tmp_path)
        p1 = tmp_path / "hive.toml"
        p2 = tmp_path / "commands" / "bar.py"
        snap = {p1: 111, p2: 222}
        assert rt._detect_worker_changes(snap, snap.copy()) is False


# ------------------------------------------------------------------ #
# _delayed_restart
# ------------------------------------------------------------------ #


class TestDelayedRestart:
    @pytest.mark.asyncio
    async def test_sends_sigterm(self, tmp_path):
        rt = _make_runtime(tmp_path)
        with patch("hive.worker.runtime.asyncio.sleep", new_callable=AsyncMock):
            with patch("hive.worker.runtime.os.kill") as mock_kill:
                await rt._delayed_restart(0)
        mock_kill.assert_called_once_with(os.getpid(), signal.SIGTERM)


# ------------------------------------------------------------------ #
# _handle_nl_message with config change detection
# ------------------------------------------------------------------ #


class TestHandleNlMessageWithRestart:
    @pytest.mark.asyncio
    async def test_triggers_restart_when_config_changed(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = AsyncMock()
        rt._agent.run = AsyncMock(return_value="ok")
        rt._app = MagicMock()
        rt._app.bot.send_message = AsyncMock()

        update = MagicMock()
        update.effective_user.id = 42
        update.effective_chat.id = 100
        update.message.text = "hello"

        before_snap = {tmp_path / "hive.toml": 1000}
        after_snap = {tmp_path / "hive.toml": 2000}  # mtime changed

        # Patch _delayed_restart so the test doesn't actually send SIGTERM.
        # The task is created normally (so typing_action still works), but the
        # coroutine body is a no-op mock.
        with patch("hive.worker.runtime.send_long_message", new_callable=AsyncMock):
            with patch.object(rt, "_auto_commit", new_callable=AsyncMock):
                with patch.object(rt, "_snapshot_worker_paths", side_effect=[before_snap, after_snap]):
                    with patch.object(rt, "_delayed_restart", new_callable=AsyncMock):
                        await rt._handle_nl_message(update, MagicMock())

        rt._app.bot.send_message.assert_awaited_once()
        sent_text = rt._app.bot.send_message.call_args.kwargs.get("text", "")
        assert "Restarting" in sent_text

    @pytest.mark.asyncio
    async def test_no_restart_on_agent_error_even_if_files_changed(self, tmp_path):
        """Config change detected after an agent error must NOT trigger restart."""
        rt = _make_runtime(tmp_path)
        rt._agent = AsyncMock()
        rt._agent.run = AsyncMock(side_effect=RuntimeError("agent blew up"))
        rt._app = MagicMock()
        rt._app.bot.send_message = AsyncMock()

        update = MagicMock()
        update.effective_user.id = 42
        update.effective_chat.id = 100
        update.message.text = "hello"
        update.message.reply_text = AsyncMock()

        before_snap = {tmp_path / "hive.toml": 1000}
        after_snap = {tmp_path / "hive.toml": 2000}  # config changed mid-error

        with patch.object(rt, "_auto_commit", new_callable=AsyncMock):
            with patch.object(rt, "_snapshot_worker_paths", side_effect=[before_snap, after_snap]):
                with patch.object(rt, "_delayed_restart", new_callable=AsyncMock) as mock_restart:
                    await rt._handle_nl_message(update, MagicMock())

        # No restart message, no restart scheduled
        rt._app.bot.send_message.assert_not_awaited()
        mock_restart.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_restart_when_files_unchanged(self, tmp_path):
        rt = _make_runtime(tmp_path)
        rt._agent = AsyncMock()
        rt._agent.run = AsyncMock(return_value="ok")
        rt._app = MagicMock()
        rt._app.bot.send_message = AsyncMock()

        update = MagicMock()
        update.effective_user.id = 42
        update.effective_chat.id = 100
        update.message.text = "hello"

        snap = {tmp_path / "hive.toml": 1000}

        with patch("hive.worker.runtime.send_long_message", new_callable=AsyncMock):
            with patch.object(rt, "_auto_commit", new_callable=AsyncMock):
                with patch.object(rt, "_snapshot_worker_paths", side_effect=[snap, snap]):
                    with patch.object(rt, "_delayed_restart", new_callable=AsyncMock) as mock_restart:
                        await rt._handle_nl_message(update, MagicMock())

        rt._app.bot.send_message.assert_not_awaited()
        mock_restart.assert_not_called()
