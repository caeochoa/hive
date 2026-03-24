"""Tests for hive.worker.builtin_tools — in-process MCP server."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from hive.worker.agent import _current_chat_id


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_runner():
    runner = MagicMock()
    runner.set_session_override = MagicMock()
    return runner


# ------------------------------------------------------------------ #
# build_builtin_mcp_server
# ------------------------------------------------------------------ #


def test_build_builtin_mcp_server_returns_dict():
    """build_builtin_mcp_server returns a McpSdkServerConfig dict."""
    from hive.worker.builtin_tools import build_builtin_mcp_server

    runner = _make_runner()
    result = build_builtin_mcp_server(runner)

    assert isinstance(result, dict)
    assert result.get("type") == "sdk"
    assert result.get("name") == "builtins"
    assert "instance" in result


# ------------------------------------------------------------------ #
# set_session_config_handler — tested by importing and calling directly
# ------------------------------------------------------------------ #


def _get_handler(runner):
    """Re-build the server and extract the handler via SdkMcpTool inspection."""
    import importlib
    import hive.worker.builtin_tools as bt_module

    # Re-import to get a fresh handler closure bound to our runner.
    # We monkey-patch the module's SdkMcpTool to capture the handler.
    captured = {}

    original_sdk = sys.modules.get("claude_agent_sdk")
    mock_sdk = MagicMock()
    mock_sdk.SdkMcpTool.side_effect = lambda name, description, input_schema, handler: (
        captured.__setitem__("handler", handler) or MagicMock()
    )
    mock_sdk.create_sdk_mcp_server.return_value = {"type": "sdk", "name": "builtins", "instance": MagicMock()}

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        bt_module.build_builtin_mcp_server(runner)

    return captured["handler"]


@pytest.mark.asyncio
async def test_set_session_config_calls_set_override():
    """Handler with a valid chat_id calls set_session_override with the right kwargs."""
    runner = _make_runner()
    handler = _get_handler(runner)

    token = _current_chat_id.set(99)
    try:
        result = await handler({"model": "claude-opus-4-6"})
    finally:
        _current_chat_id.reset(token)

    runner.set_session_override.assert_called_once_with(99, model="claude-opus-4-6")
    assert result.get("is_error") is not True
    assert "updated" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_set_session_config_no_chat_id_returns_error():
    """Handler with no active chat_id (ContextVar unset) returns an error."""
    runner = _make_runner()
    handler = _get_handler(runner)

    # _current_chat_id defaults to None
    result = await handler({"model": "claude-opus-4-6"})

    assert result.get("is_error") is True
    runner.set_session_override.assert_not_called()


@pytest.mark.asyncio
async def test_set_session_config_partial_args_only_max_turns():
    """Handler with only max_turns passes only that kwarg."""
    runner = _make_runner()
    handler = _get_handler(runner)

    token = _current_chat_id.set(55)
    try:
        await handler({"max_turns": 15})
    finally:
        _current_chat_id.reset(token)

    runner.set_session_override.assert_called_once_with(55, max_turns=15)


@pytest.mark.asyncio
async def test_set_session_config_thinking_budget():
    """thinking_budget_tokens is passed through as an integer."""
    runner = _make_runner()
    handler = _get_handler(runner)

    token = _current_chat_id.set(66)
    try:
        await handler({"thinking_budget_tokens": 8000})
    finally:
        _current_chat_id.reset(token)

    runner.set_session_override.assert_called_once_with(66, thinking_budget_tokens=8000)


@pytest.mark.asyncio
async def test_set_session_config_empty_args_returns_no_change():
    """Handler with no recognised fields returns a 'nothing changed' message."""
    runner = _make_runner()
    handler = _get_handler(runner)

    token = _current_chat_id.set(77)
    try:
        result = await handler({})
    finally:
        _current_chat_id.reset(token)

    runner.set_session_override.assert_not_called()
    assert result.get("is_error") is not True
    assert "nothing" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_set_session_config_none_values_ignored():
    """None values in args are treated as absent (not passed to set_session_override)."""
    runner = _make_runner()
    handler = _get_handler(runner)

    token = _current_chat_id.set(88)
    try:
        await handler({"model": None, "max_turns": 5})
    finally:
        _current_chat_id.reset(token)

    # Only max_turns should be passed, model=None is skipped
    runner.set_session_override.assert_called_once_with(88, max_turns=5)
