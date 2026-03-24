"""In-process MCP server exposing built-in agent tools (set_session_config, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hive.worker.agent import _current_chat_id

if TYPE_CHECKING:
    from hive.worker.agent import ClaudeAgentRunner


def build_builtin_mcp_server(runner: ClaudeAgentRunner) -> Any:
    """Return an in-process MCP server with Hive built-in tools for the agent.

    The returned server is a McpSdkServerConfig dict, suitable for passing as
    a value in ClaudeAgentOptions.mcp_servers.
    """
    from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server

    async def set_session_config_handler(args: dict[str, Any]) -> dict[str, Any]:
        """Handle set_session_config tool calls from the agent."""
        chat_id = _current_chat_id.get()
        if chat_id is None:
            return {
                "content": [{"type": "text", "text": "Error: no active chat session context"}],
                "is_error": True,
            }

        overrides: dict[str, Any] = {}
        if args.get("model") is not None:
            overrides["model"] = str(args["model"])
        if args.get("max_turns") is not None:
            overrides["max_turns"] = int(args["max_turns"])
        if args.get("thinking_budget_tokens") is not None:
            overrides["thinking_budget_tokens"] = int(args["thinking_budget_tokens"])

        if not overrides:
            return {
                "content": [{"type": "text", "text": "No config values provided — nothing changed."}]
            }

        runner.set_session_override(chat_id, **overrides)
        applied = ", ".join(f"{k}={v}" for k, v in overrides.items())
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Session config updated: {applied}. "
                        "Changes take effect from the next message. "
                        "Overrides reset on /reset or worker restart."
                    ),
                }
            ]
        }

    tool = SdkMcpTool(
        name="set_session_config",
        description=(
            "Override agent configuration for the current Telegram chat session. "
            "Supported fields: model (Claude model ID string), max_turns (integer), "
            "thinking_budget_tokens (integer). Overrides are in-memory only and reset "
            "on /reset or worker restart. Changes take effect from the next message."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Claude model ID to use for this session (e.g. claude-opus-4-6)",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum agent turns per message for this session",
                },
                "thinking_budget_tokens": {
                    "type": "integer",
                    "description": "Extended thinking token budget for this session (0 to disable)",
                },
            },
        },
        handler=set_session_config_handler,
    )

    return create_sdk_mcp_server("builtins", tools=[tool])
