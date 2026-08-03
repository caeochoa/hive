"""In-process MCP server exposing built-in agent tools (set_session_config, write_page)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hive.worker.agent import _current_chat_id
from hive.worker.knowledge import write_page

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

    async def write_page_handler(args: dict[str, Any]) -> dict[str, Any]:
        """Handle write_page tool calls from the agent."""
        slug = str(args.get("slug", ""))
        title = str(args.get("title", ""))
        summary = str(args.get("summary", ""))
        content = str(args.get("content", ""))

        missing = [
            name
            for name, value in (
                ("slug", slug), ("title", title), ("summary", summary), ("content", content),
            )
            if not value
        ]
        if missing:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: missing required field(s): {', '.join(missing)}",
                    }
                ],
                "is_error": True,
            }

        try:
            write_page(runner.memory_dir, slug, title, summary, content)
        except ValueError as exc:
            return {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "is_error": True,
            }

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Saved memory/notes/{slug}.md and updated memory/index.md.",
                }
            ]
        }

    set_session_config_tool = SdkMcpTool(
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

    write_page_tool = SdkMcpTool(
        name="write_page",
        description=(
            "Save or update a durable knowledge page under memory/notes/. Use this when "
            "you've produced a synthesis, answer, or understanding worth keeping — not for "
            "routine notes. If a page on this topic already exists (check with Glob/Grep/Read "
            "on memory/notes/ first), prefer updating it over creating a near-duplicate — read "
            "it first so you don't drop existing content. Overwrites are safe: every write is "
            "auto-committed to git, so prior versions are always recoverable."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Kebab-case page id, e.g. 'thompson-thesis' (lowercase letters, digits, hyphens only)",
                },
                "title": {
                    "type": "string",
                    "description": "Human-readable page title",
                },
                "summary": {
                    "type": "string",
                    "description": "One-line summary shown in memory/index.md",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown body of the page",
                },
            },
            "required": ["slug", "title", "summary", "content"],
        },
        handler=write_page_handler,
    )

    return create_sdk_mcp_server("builtins", tools=[set_session_config_tool, write_page_tool])
