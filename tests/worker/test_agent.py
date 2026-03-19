"""Tests for hive.worker.agent module."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.worker.agent import AgentRunner, ClaudeAgentRunner


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def agent_config():
    return SimpleNamespace(
        model="claude-haiku-4-5",
        system_prompt="Test system prompt",
        max_turns=5,
        memory_dir="memory/",
    )


@pytest.fixture()
def sessions_file(tmp_path: Path) -> Path:
    return tmp_path / "sessions.json"


@pytest.fixture()
def worker_dir(tmp_path: Path) -> Path:
    d = tmp_path / "worker"
    d.mkdir()
    return d


@pytest.fixture()
def commands_mcp():
    return MagicMock()


@pytest.fixture()
def runner(agent_config, commands_mcp, sessions_file, worker_dir):
    return ClaudeAgentRunner(
        config=agent_config,
        commands_mcp=commands_mcp,
        command_names=[],
        sessions_file=sessions_file,
        worker_dir=worker_dir,
    )


# ------------------------------------------------------------------ #
# ABC
# ------------------------------------------------------------------ #


def test_agent_runner_is_abstract():
    with pytest.raises(TypeError):
        AgentRunner()  # type: ignore[abstract]


# ------------------------------------------------------------------ #
# Session load / save
# ------------------------------------------------------------------ #


def test_load_sessions_no_file(runner, sessions_file):
    """When sessions file doesn't exist, sessions dict is empty."""
    assert runner._sessions == {}


def test_load_sessions_from_file(agent_config, commands_mcp, worker_dir, tmp_path):
    """Sessions are loaded from an existing JSON file."""
    sf = tmp_path / "sessions.json"
    sf.write_text(
        json.dumps([{"chat_id": 42, "session_id": "sess-abc"}])
    )
    r = ClaudeAgentRunner(
        config=agent_config,
        commands_mcp=commands_mcp,
        command_names=[],
        sessions_file=sf,
        worker_dir=worker_dir,
    )
    assert 42 in r._sessions
    assert r._sessions[42]["session_id"] == "sess-abc"


def test_load_sessions_corrupt_file(agent_config, commands_mcp, worker_dir, tmp_path):
    """Corrupt JSON in sessions file results in empty sessions."""
    sf = tmp_path / "sessions.json"
    sf.write_text("NOT-JSON")
    r = ClaudeAgentRunner(
        config=agent_config,
        commands_mcp=commands_mcp,
        command_names=[],
        sessions_file=sf,
        worker_dir=worker_dir,
    )
    assert r._sessions == {}


def test_save_sessions(runner, sessions_file):
    """Saving sessions writes valid JSON to disk."""
    runner._sessions[10] = {"chat_id": 10, "session_id": "s10"}
    runner._sessions[20] = {"chat_id": 20, "session_id": "s20"}
    runner._save_sessions()

    data = json.loads(sessions_file.read_text())
    assert len(data) == 2
    ids = {d["chat_id"] for d in data}
    assert ids == {10, 20}


# ------------------------------------------------------------------ #
# Locking
# ------------------------------------------------------------------ #


def test_get_lock_creates_per_chat(runner):
    """Each chat_id gets its own lock, and repeated calls return the same lock."""
    lock_a = runner._get_lock(1)
    lock_b = runner._get_lock(2)
    assert lock_a is not lock_b
    assert runner._get_lock(1) is lock_a


# ------------------------------------------------------------------ #
# One-shot path (chat_id=None)
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_run_one_shot(runner, worker_dir):
    """chat_id=None triggers the one-shot path with a disposable client."""
    mock_result = MagicMock()
    mock_result.response = "one-shot reply"

    mock_client_cls = MagicMock()
    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client_instance

    mock_options_cls = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "claude_agent_sdk": MagicMock(
                ClaudeSDKClient=mock_client_cls,
                ClaudeAgentOptions=mock_options_cls,
                query=AsyncMock(return_value=mock_result),
            ),
        },
    ):
        result = await runner.run("hello", chat_id=None, worker_dir=worker_dir)

    assert result == "one-shot reply"


# ------------------------------------------------------------------ #
# Interactive path (chat_id != None)
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_run_interactive(runner, worker_dir, sessions_file):
    """chat_id != None triggers the interactive path and persists session."""
    mock_result = MagicMock()
    mock_result.response = "interactive reply"

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.session_id = "new-session-id"

    mock_client_cls = MagicMock(return_value=mock_client_instance)
    mock_options_cls = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "claude_agent_sdk": MagicMock(
                ClaudeSDKClient=mock_client_cls,
                ClaudeAgentOptions=mock_options_cls,
                query=AsyncMock(return_value=mock_result),
            ),
        },
    ):
        result = await runner.run("hi there", chat_id=99, worker_dir=worker_dir)

    assert result == "interactive reply"
    # Session should be saved
    assert 99 in runner._sessions
    assert runner._sessions[99]["session_id"] == "new-session-id"
    # File should exist on disk
    assert sessions_file.exists()


# ------------------------------------------------------------------ #
# Reset session
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_reset_session(runner, sessions_file):
    """reset_session clears client, stack, session, and lock."""
    # Set up some state
    runner._sessions[5] = {"chat_id": 5, "session_id": "s5"}
    runner._clients[5] = MagicMock()
    runner._locks[5] = asyncio.Lock()

    mock_stack = AsyncMock()
    runner._exit_stacks[5] = mock_stack

    await runner.reset_session(5)

    assert 5 not in runner._sessions
    assert 5 not in runner._clients
    assert 5 not in runner._exit_stacks
    assert 5 not in runner._locks
    mock_stack.aclose.assert_awaited_once()
    # Sessions file saved (should be empty now)
    data = json.loads(sessions_file.read_text())
    assert data == []


# ------------------------------------------------------------------ #
# Close
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_close_all(runner, sessions_file):
    """close() closes all stacks and saves sessions."""
    runner._sessions[1] = {"chat_id": 1, "session_id": "s1"}
    runner._clients[1] = MagicMock()

    mock_stack = AsyncMock()
    runner._exit_stacks[1] = mock_stack

    await runner.close()

    mock_stack.aclose.assert_awaited_once()
    assert runner._exit_stacks == {}
    assert runner._clients == {}
    # Sessions still saved
    assert sessions_file.exists()
    data = json.loads(sessions_file.read_text())
    assert len(data) == 1
    assert data[0]["session_id"] == "s1"
