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
    """Re-build the server and extract the set_session_config handler by name.

    The server now registers multiple tools, so handlers are captured by
    name rather than by "last SdkMcpTool call wins".
    """
    import hive.worker.builtin_tools as bt_module

    captured: dict[str, object] = {}

    def _capture(name, description, input_schema, handler):
        captured[name] = handler
        return MagicMock()

    mock_sdk = MagicMock()
    mock_sdk.SdkMcpTool.side_effect = _capture
    mock_sdk.create_sdk_mcp_server.return_value = {"type": "sdk", "name": "builtins", "instance": MagicMock()}

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        bt_module.build_builtin_mcp_server(runner)

    return captured["set_session_config"]


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


# ------------------------------------------------------------------ #
# write_page_handler
# ------------------------------------------------------------------ #


def _get_write_page_handler(runner):
    """Re-build the server, capturing every SdkMcpTool's handler by name."""
    import hive.worker.builtin_tools as bt_module

    captured: dict[str, object] = {}

    def _capture(name, description, input_schema, handler):
        captured[name] = handler
        return MagicMock()

    mock_sdk = MagicMock()
    mock_sdk.SdkMcpTool.side_effect = _capture
    mock_sdk.create_sdk_mcp_server.return_value = {"type": "sdk", "name": "builtins", "instance": MagicMock()}

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        bt_module.build_builtin_mcp_server(runner)

    return captured["write_page"]


@pytest.mark.asyncio
async def test_write_page_handler_calls_knowledge_write_page(tmp_path):
    """Handler delegates to knowledge.write_page with the runner's memory_dir."""
    runner = _make_runner()
    runner.memory_dir = tmp_path
    handler = _get_write_page_handler(runner)

    result = await handler({
        "slug": "thompson-thesis",
        "title": "Thompson's Thesis",
        "summary": "Evolving view on X",
        "content": "# Body",
    })

    assert result.get("is_error") is not True
    assert (tmp_path / "notes" / "thompson-thesis.md").read_text() == "# Body"
    assert "thompson-thesis" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_write_page_handler_invalid_slug_returns_error(tmp_path):
    """Handler surfaces knowledge.write_page's ValueError as an MCP error result, not an exception."""
    runner = _make_runner()
    runner.memory_dir = tmp_path
    handler = _get_write_page_handler(runner)

    result = await handler({
        "slug": "../escape",
        "title": "Title",
        "summary": "Summary",
        "content": "body",
    })

    assert result.get("is_error") is True
    assert not (tmp_path / "notes").exists()


@pytest.mark.asyncio
async def test_write_page_handler_missing_title_returns_error(tmp_path):
    """A missing (absent) title field is caught before write_page is called."""
    runner = _make_runner()
    runner.memory_dir = tmp_path
    handler = _get_write_page_handler(runner)

    result = await handler({
        "slug": "thompson-thesis",
        "summary": "Evolving view on X",
        "content": "# Body",
    })

    assert result.get("is_error") is True
    assert "title" in result["content"][0]["text"]
    assert not (tmp_path / "notes").exists()


@pytest.mark.asyncio
async def test_write_page_handler_empty_content_returns_error(tmp_path):
    """A present-but-empty content field is treated as missing, not written as an empty note."""
    runner = _make_runner()
    runner.memory_dir = tmp_path
    handler = _get_write_page_handler(runner)

    result = await handler({
        "slug": "thompson-thesis",
        "title": "Thompson's Thesis",
        "summary": "Evolving view on X",
        "content": "",
    })

    assert result.get("is_error") is True
    assert "content" in result["content"][0]["text"]
    assert not (tmp_path / "notes").exists()


@pytest.mark.asyncio
async def test_write_page_handler_multiple_missing_fields_lists_all(tmp_path):
    """When several fields are missing, the error names all of them."""
    runner = _make_runner()
    runner.memory_dir = tmp_path
    handler = _get_write_page_handler(runner)

    result = await handler({"slug": "thompson-thesis"})

    assert result.get("is_error") is True
    text = result["content"][0]["text"]
    assert "title" in text
    assert "summary" in text
    assert "content" in text
