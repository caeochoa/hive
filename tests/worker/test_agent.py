"""Tests for hive.worker.agent module."""

from __future__ import annotations

import asyncio
import json
import logging
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
    """chat_id=None triggers the one-shot path and collects TextBlock text."""
    # Build mock types for isinstance checks
    TextBlock = type("TextBlock", (), {})
    AssistantMessage = type("AssistantMessage", (), {})
    DummyMsg = type("DummyMsg", (), {})

    text_block = TextBlock()
    text_block.text = "one-shot reply"
    assistant_msg = AssistantMessage()
    assistant_msg.content = [text_block]

    async def mock_query(**kwargs):
        yield assistant_msg

    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(return_value=MagicMock()),
        ClaudeSDKClient=MagicMock(),
        AssistantMessage=AssistantMessage,
        UserMessage=DummyMsg,
        ResultMessage=DummyMsg,
        ThinkingBlock=DummyMsg,
        ToolUseBlock=DummyMsg,
        ToolResultBlock=DummyMsg,
        TextBlock=TextBlock,
    )
    mock_sdk.query = MagicMock(return_value=mock_query())

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        result = await runner.run("hello", chat_id=None, worker_dir=worker_dir)

    assert result == "one-shot reply"


# ------------------------------------------------------------------ #
# Interactive path (chat_id != None)
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_run_interactive(runner, worker_dir, sessions_file):
    """chat_id != None triggers the interactive path and persists session."""
    TextBlock = type("TextBlock", (), {})
    AssistantMessage = type("AssistantMessage", (), {})
    ResultMessage = type("ResultMessage", (), {})
    DummyMsg = type("DummyMsg", (), {})

    text_block = TextBlock()
    text_block.text = "interactive reply"
    assistant_msg = AssistantMessage()
    assistant_msg.content = [text_block]
    result_msg = ResultMessage()
    result_msg.session_id = "new-session-id"
    result_msg.num_turns = 1
    result_msg.total_cost_usd = None
    result_msg.stop_reason = "end_turn"
    result_msg.usage = None

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.receive_response = MagicMock(return_value=mock_receive())

    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(return_value=MagicMock()),
        ClaudeSDKClient=MagicMock(return_value=mock_client_instance),
        AssistantMessage=AssistantMessage,
        UserMessage=DummyMsg,
        ResultMessage=ResultMessage,
        ThinkingBlock=DummyMsg,
        ToolUseBlock=DummyMsg,
        ToolResultBlock=DummyMsg,
        TextBlock=TextBlock,
    )

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        result = await runner.run("hi there", chat_id=99, worker_dir=worker_dir)

    assert result == "interactive reply"
    assert 99 in runner._sessions
    assert runner._sessions[99]["session_id"] == "new-session-id"
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


# ------------------------------------------------------------------ #
# _log_sdk_message
# ------------------------------------------------------------------ #


def _make_sdk_mocks():
    """Build mock SDK classes that mimic the real types."""
    TextBlock = type("TextBlock", (), {})
    ThinkingBlock = type("ThinkingBlock", (), {})
    ToolUseBlock = type("ToolUseBlock", (), {})
    ToolResultBlock = type("ToolResultBlock", (), {})

    class AssistantMessage:
        def __init__(self, content):
            self.content = content

    class UserMessage:
        def __init__(self, content):
            self.content = content

    class ResultMessage:
        def __init__(self, num_turns, total_cost_usd, stop_reason, usage=None):
            self.num_turns = num_turns
            self.total_cost_usd = total_cost_usd
            self.stop_reason = stop_reason
            self.usage = usage
            self.session_id = "sess-123"
            self.is_error = False

    return {
        "AssistantMessage": AssistantMessage,
        "UserMessage": UserMessage,
        "ResultMessage": ResultMessage,
        "TextBlock": TextBlock,
        "ThinkingBlock": ThinkingBlock,
        "ToolUseBlock": ToolUseBlock,
        "ToolResultBlock": ToolResultBlock,
    }


def test_log_sdk_message_tool_use(runner, caplog):
    """ToolUseBlock in AssistantMessage logs [tool_use] at INFO."""
    mocks = _make_sdk_mocks()

    tool_block = mocks["ToolUseBlock"]()
    tool_block.name = "Read"
    tool_block.input = {"file_path": "/foo/bar.md"}
    msg = mocks["AssistantMessage"](content=[tool_block])

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock(**mocks)}):
        with caplog.at_level(logging.INFO, logger="hive.worker.agent"):
            runner._log_sdk_message(msg)

    assert any("[tool_use]" in r.message and "Read" in r.message for r in caplog.records)


def test_log_sdk_message_tool_result_ok(runner, caplog):
    """ToolResultBlock (no error) in UserMessage logs [tool_result] at INFO."""
    mocks = _make_sdk_mocks()

    result_block = mocks["ToolResultBlock"]()
    result_block.tool_use_id = "abc12345"
    result_block.content = "file contents here"
    result_block.is_error = False
    msg = mocks["UserMessage"](content=[result_block])

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock(**mocks)}):
        with caplog.at_level(logging.INFO, logger="hive.worker.agent"):
            runner._log_sdk_message(msg)

    assert any("[tool_result]" in r.message for r in caplog.records)
    assert not any("[tool_error]" in r.message for r in caplog.records)


def test_log_sdk_message_tool_result_error(runner, caplog):
    """ToolResultBlock with is_error=True logs [tool_error] at ERROR."""
    mocks = _make_sdk_mocks()

    result_block = mocks["ToolResultBlock"]()
    result_block.tool_use_id = "abc12345"
    result_block.content = "No such file"
    result_block.is_error = True
    msg = mocks["UserMessage"](content=[result_block])

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock(**mocks)}):
        with caplog.at_level(logging.ERROR, logger="hive.worker.agent"):
            runner._log_sdk_message(msg)

    assert any("[tool_error]" in r.message for r in caplog.records)


def test_log_sdk_message_thinking(runner, caplog):
    """ThinkingBlock in AssistantMessage logs [thinking] at INFO."""
    mocks = _make_sdk_mocks()

    think_block = mocks["ThinkingBlock"]()
    think_block.thinking = "Let me reason about this carefully..."
    msg = mocks["AssistantMessage"](content=[think_block])

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock(**mocks)}):
        with caplog.at_level(logging.INFO, logger="hive.worker.agent"):
            runner._log_sdk_message(msg)

    assert any("[thinking]" in r.message for r in caplog.records)


def test_log_sdk_message_result(runner, caplog):
    """ResultMessage logs [result] with turns, cost, and stop_reason at INFO."""
    mocks = _make_sdk_mocks()
    msg = mocks["ResultMessage"](num_turns=3, total_cost_usd=0.0021, stop_reason="end_turn")

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock(**mocks)}):
        with caplog.at_level(logging.INFO, logger="hive.worker.agent"):
            runner._log_sdk_message(msg)

    assert any(
        "[result]" in r.message and "turns=3" in r.message and "end_turn" in r.message
        for r in caplog.records
    )


def test_log_sdk_message_result_no_cost(runner, caplog):
    """ResultMessage with total_cost_usd=None logs cost as 'n/a'."""
    mocks = _make_sdk_mocks()
    msg = mocks["ResultMessage"](num_turns=1, total_cost_usd=None, stop_reason="max_turns")

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock(**mocks)}):
        with caplog.at_level(logging.INFO, logger="hive.worker.agent"):
            runner._log_sdk_message(msg)

    assert any("[result]" in r.message and "n/a" in r.message for r in caplog.records)


# ------------------------------------------------------------------ #
# thinking kwarg wiring
# ------------------------------------------------------------------ #


async def _async_empty():
    """Helper: empty async generator for mocking query()."""
    return
    yield  # noqa: unreachable — makes this an async generator


@pytest.mark.asyncio
async def test_thinking_kwarg_not_passed_when_none(runner):
    """When thinking_budget_tokens is absent, 'thinking' kwarg is not passed to ClaudeAgentOptions."""
    options_kwargs = {}

    def capture_kwargs(**kwargs):
        options_kwargs.update(kwargs)
        return MagicMock()

    DummyMsg = type("AssistantMessage", (), {})
    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(side_effect=capture_kwargs),
        ClaudeSDKClient=MagicMock(),
        AssistantMessage=DummyMsg,
        UserMessage=DummyMsg,
        ResultMessage=DummyMsg,
        ThinkingBlock=type("ThinkingBlock", (), {}),
        ToolUseBlock=type("ToolUseBlock", (), {}),
        ToolResultBlock=type("ToolResultBlock", (), {}),
        TextBlock=type("TextBlock", (), {}),
    )
    mock_sdk.query = MagicMock(return_value=_async_empty())

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        await runner._run_one_shot("test")

    assert "thinking" not in options_kwargs


@pytest.mark.asyncio
async def test_thinking_kwarg_passed_when_set(agent_config, commands_mcp, sessions_file, worker_dir):
    """When thinking_budget_tokens is set, 'thinking' dict is passed to ClaudeAgentOptions."""
    agent_config.thinking_budget_tokens = 5000
    r = ClaudeAgentRunner(
        config=agent_config,
        commands_mcp=commands_mcp,
        command_names=[],
        sessions_file=sessions_file,
        worker_dir=worker_dir,
    )

    options_kwargs = {}

    def capture_kwargs(**kwargs):
        options_kwargs.update(kwargs)
        return MagicMock()

    DummyMsg = type("AssistantMessage", (), {})
    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(side_effect=capture_kwargs),
        ClaudeSDKClient=MagicMock(),
        AssistantMessage=DummyMsg,
        UserMessage=DummyMsg,
        ResultMessage=DummyMsg,
        ThinkingBlock=type("ThinkingBlock", (), {}),
        ToolUseBlock=type("ToolUseBlock", (), {}),
        ToolResultBlock=type("ToolResultBlock", (), {}),
        TextBlock=type("TextBlock", (), {}),
    )
    mock_sdk.query = MagicMock(return_value=_async_empty())

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        await r._run_one_shot("test")

    assert options_kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 5000}


# ------------------------------------------------------------------ #
# _close_client helper
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_close_client_removes_client_and_stack(runner):
    """_close_client removes both client and exit stack without touching sessions."""
    runner._sessions[7] = {"chat_id": 7, "session_id": "s7"}
    runner._clients[7] = MagicMock()
    mock_stack = AsyncMock()
    runner._exit_stacks[7] = mock_stack

    await runner._close_client(7)

    mock_stack.aclose.assert_awaited_once()
    assert 7 not in runner._clients
    assert 7 not in runner._exit_stacks
    # Session data is preserved
    assert 7 in runner._sessions


@pytest.mark.asyncio
async def test_close_client_noop_when_no_client(runner):
    """_close_client is a no-op when there is no active client."""
    # Should not raise
    await runner._close_client(999)


# ------------------------------------------------------------------ #
# Session overrides
# ------------------------------------------------------------------ #


def test_set_session_override_stores_override(runner):
    runner.set_session_override(42, model="claude-opus-4-6")
    assert runner._session_overrides[42] == {"model": "claude-opus-4-6"}
    assert 42 in runner._pending_override_reset


def test_set_session_override_multiple_keys(runner):
    runner.set_session_override(42, model="claude-opus-4-6", max_turns=20)
    assert runner._session_overrides[42] == {"model": "claude-opus-4-6", "max_turns": 20}


def test_set_session_override_merges_sequential_calls(runner):
    """Sequential calls accumulate overrides rather than replacing them."""
    runner.set_session_override(42, model="claude-opus-4-6")
    runner.set_session_override(42, max_turns=20)
    assert runner._session_overrides[42] == {"model": "claude-opus-4-6", "max_turns": 20}


# ------------------------------------------------------------------ #
# set_builtins_mcp setter
# ------------------------------------------------------------------ #


def test_set_builtins_mcp_stores_server(runner):
    """set_builtins_mcp() assigns to _builtins_mcp (no private attr mutation)."""
    server = object()
    runner.set_builtins_mcp(server)
    assert runner._builtins_mcp is server


def test_clear_session_override_removes_state(runner):
    runner.set_session_override(42, model="claude-opus-4-6")
    runner.clear_session_override(42)
    assert 42 not in runner._session_overrides
    assert 42 not in runner._pending_override_reset


def test_clear_session_override_noop_when_absent(runner):
    # Should not raise
    runner.clear_session_override(999)


@pytest.mark.asyncio
async def test_reset_session_clears_overrides(runner, sessions_file):
    runner._sessions[5] = {"chat_id": 5, "session_id": "s5"}
    runner._clients[5] = MagicMock()
    runner._locks[5] = asyncio.Lock()
    runner._exit_stacks[5] = AsyncMock()
    runner.set_session_override(5, model="claude-opus-4-6")

    await runner.reset_session(5)

    assert 5 not in runner._session_overrides
    assert 5 not in runner._pending_override_reset


# ------------------------------------------------------------------ #
# _get_or_create_client merges overrides
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_get_or_create_client_merges_model_override(runner):
    """Session model override replaces the config model in ClaudeAgentOptions."""
    runner.set_session_override(42, model="claude-opus-4-6")
    # Clear pending reset so _get_or_create_client is called (not skipped)
    runner._pending_override_reset.discard(42)

    options_kwargs: dict = {}

    def capture(**kwargs):
        options_kwargs.update(kwargs)
        return MagicMock()

    DummyMsg = type("DummyMsg", (), {})
    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(side_effect=capture),
        ClaudeSDKClient=MagicMock(),
        AssistantMessage=DummyMsg,
        UserMessage=DummyMsg,
        ResultMessage=DummyMsg,
        ThinkingBlock=DummyMsg,
        ToolUseBlock=DummyMsg,
        ToolResultBlock=DummyMsg,
        TextBlock=DummyMsg,
    )

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        await runner._get_or_create_client(42)

    assert options_kwargs.get("model") == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_get_or_create_client_merges_thinking_override(runner):
    """thinking_budget_tokens override is converted to the nested thinking dict."""
    runner.set_session_override(42, thinking_budget_tokens=3000)
    runner._pending_override_reset.discard(42)

    options_kwargs: dict = {}

    def capture(**kwargs):
        options_kwargs.update(kwargs)
        return MagicMock()

    DummyMsg = type("DummyMsg", (), {})
    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(side_effect=capture),
        ClaudeSDKClient=MagicMock(),
        AssistantMessage=DummyMsg,
        UserMessage=DummyMsg,
        ResultMessage=DummyMsg,
        ThinkingBlock=DummyMsg,
        ToolUseBlock=DummyMsg,
        ToolResultBlock=DummyMsg,
        TextBlock=DummyMsg,
    )

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        await runner._get_or_create_client(42)

    assert options_kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 3000}
    assert "thinking_budget_tokens" not in options_kwargs


# ------------------------------------------------------------------ #
# _run_interactive: pending override reset closes stale client
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_pending_override_reset_closes_stale_client(runner, worker_dir):
    """When _pending_override_reset contains chat_id, the old client is closed first."""
    # Pre-install a fake client and exit stack
    mock_stack = AsyncMock()
    runner._exit_stacks[42] = mock_stack
    runner._clients[42] = MagicMock()
    runner._pending_override_reset.add(42)

    TextBlock = type("TextBlock", (), {})
    AssistantMessage = type("AssistantMessage", (), {})
    ResultMessage = type("ResultMessage", (), {})
    DummyMsg = type("DummyMsg", (), {})

    text_block = TextBlock()
    text_block.text = "reply"
    assistant_msg = AssistantMessage()
    assistant_msg.content = [text_block]
    result_msg = ResultMessage()
    result_msg.session_id = "new-sess"
    result_msg.num_turns = 1
    result_msg.total_cost_usd = None
    result_msg.stop_reason = "end_turn"
    result_msg.usage = None

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    new_client = AsyncMock()
    new_client.__aenter__ = AsyncMock(return_value=new_client)
    new_client.__aexit__ = AsyncMock(return_value=False)
    new_client.receive_response = MagicMock(return_value=mock_receive())

    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(return_value=MagicMock()),
        ClaudeSDKClient=MagicMock(return_value=new_client),
        AssistantMessage=AssistantMessage,
        UserMessage=DummyMsg,
        ResultMessage=ResultMessage,
        ThinkingBlock=DummyMsg,
        ToolUseBlock=DummyMsg,
        ToolResultBlock=DummyMsg,
        TextBlock=TextBlock,
    )

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        await runner._run_interactive("hello", 42)

    # Old exit stack should have been closed
    mock_stack.aclose.assert_awaited_once()
    # pending_override_reset cleared
    assert 42 not in runner._pending_override_reset


@pytest.mark.asyncio
async def test_contextvar_set_during_run_interactive(runner, worker_dir):
    """_current_chat_id ContextVar holds the correct chat_id during a turn."""
    from hive.worker.agent import _current_chat_id

    captured_chat_id = []

    TextBlock = type("TextBlock", (), {})
    AssistantMessage = type("AssistantMessage", (), {})
    ResultMessage = type("ResultMessage", (), {})
    DummyMsg = type("DummyMsg", (), {})

    text_block = TextBlock()
    text_block.text = "hi"
    assistant_msg = AssistantMessage()
    assistant_msg.content = [text_block]
    result_msg = ResultMessage()
    result_msg.session_id = "sess-cv"
    result_msg.num_turns = 1
    result_msg.total_cost_usd = None
    result_msg.stop_reason = "end_turn"
    result_msg.usage = None

    async def mock_receive():
        # Capture the ContextVar value mid-turn
        captured_chat_id.append(_current_chat_id.get())
        yield assistant_msg
        yield result_msg

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.receive_response = MagicMock(return_value=mock_receive())

    mock_sdk = MagicMock(
        ClaudeAgentOptions=MagicMock(return_value=MagicMock()),
        ClaudeSDKClient=MagicMock(return_value=mock_client),
        AssistantMessage=AssistantMessage,
        UserMessage=DummyMsg,
        ResultMessage=ResultMessage,
        ThinkingBlock=DummyMsg,
        ToolUseBlock=DummyMsg,
        ToolResultBlock=DummyMsg,
        TextBlock=TextBlock,
    )

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        await runner._run_interactive("hello", 77)

    assert captured_chat_id == [77]
    # ContextVar reset after the turn
    assert _current_chat_id.get() is None


# ------------------------------------------------------------------ #
# _try_capture_result_usage
# ------------------------------------------------------------------ #


class TestTryCaptureResultUsage:
    """Unit tests for ClaudeAgentRunner._try_capture_result_usage."""

    @pytest.fixture()
    def store(self, tmp_path: Path):
        from hive.worker.usage import UsageStore
        return UsageStore(path=tmp_path / "usage.json")

    @pytest.fixture()
    def runner_with_store(self, agent_config, commands_mcp, sessions_file, worker_dir, store):
        r = ClaudeAgentRunner(
            config=agent_config,
            commands_mcp=commands_mcp,
            command_names=[],
            sessions_file=sessions_file,
            worker_dir=worker_dir,
            usage_store=store,
        )
        return r, store

    def test_no_usage_store_is_noop(self, runner):
        """When usage_store is None, calling the method doesn't raise."""
        runner._try_capture_result_usage({"rate_limits": {"five_hour": {"percent_used": 50.0}}})

    def test_none_usage_logs_warning(self, runner_with_store, caplog):
        r, store = runner_with_store
        with caplog.at_level(logging.WARNING, logger="hive.worker.agent"):
            r._try_capture_result_usage(None)
        assert store.load() is None
        assert "empty" in caplog.text

    def test_empty_dict_logs_warning(self, runner_with_store, caplog):
        r, store = runner_with_store
        with caplog.at_level(logging.WARNING, logger="hive.worker.agent"):
            r._try_capture_result_usage({})
        assert store.load() is None

    def test_nested_rate_limits_structure(self, runner_with_store):
        r, store = runner_with_store
        usage = {
            "input_tokens": 100,
            "rate_limits": {
                "five_hour": {"percent_used": 60.5},
                "seven_day": {"percent_used": 82.0},
            },
        }
        r._try_capture_result_usage(usage)
        data = store.load()
        assert data is not None
        assert data["five_hour_pct"] == pytest.approx(60.5)
        assert data["seven_day_pct"] == pytest.approx(82.0)

    def test_flat_keys_structure(self, runner_with_store):
        r, store = runner_with_store
        usage = {"five_hour_pct": 55.0, "seven_day_pct": 78.0, "input_tokens": 200}
        r._try_capture_result_usage(usage)
        data = store.load()
        assert data is not None
        assert data["five_hour_pct"] == pytest.approx(55.0)
        assert data["seven_day_pct"] == pytest.approx(78.0)

    def test_unknown_structure_logs_warning(self, runner_with_store, caplog):
        r, store = runner_with_store
        with caplog.at_level(logging.WARNING, logger="hive.worker.agent"):
            r._try_capture_result_usage({"input_tokens": 100, "output_tokens": 50})
        assert store.load() is None
        assert "no rate-limit percentages" in caplog.text

    def test_partial_nested_only_five_hour(self, runner_with_store):
        r, store = runner_with_store
        usage = {"rate_limits": {"five_hour": {"percent_used": 70.0}}}
        r._try_capture_result_usage(usage)
        data = store.load()
        assert data is not None
        assert data["five_hour_pct"] == pytest.approx(70.0)
        assert data["seven_day_pct"] is None
