"""Agent runner abstraction and Claude Agent SDK implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from hive.shared.models import AgentSession

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are a worker agent. Your world is this folder."
    "\n\nYou may modify hive.toml to change your configuration (model, schedules, "
    "comb cells, etc.) and create or edit files in commands/ to add or update your tools. "
    "After any such changes, the worker will automatically restart to apply them; "
    "your conversation session persists across restarts."
    "\n\nYou also have a set_session_config tool to temporarily override model, "
    "max_turns, or thinking_budget_tokens for the current conversation. "
    "These overrides reset on /reset or worker restart."
)

# ContextVar set by _run_interactive so builtin MCP tools can identify the caller.
_current_chat_id: ContextVar[int | None] = ContextVar("_current_chat_id", default=None)


class AgentRunner(ABC):
    """Abstract base class for agent runners."""

    @abstractmethod
    async def run(self, message: str, chat_id: int | None, worker_dir: Path) -> str:
        """Run the agent with a message and return the response."""

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""


class ClaudeAgentRunner(AgentRunner):
    """Agent runner backed by the Claude Agent SDK."""

    def __init__(
        self,
        config: Any,
        commands_mcp: Any,
        command_names: list[str],
        sessions_file: Path,
        worker_dir: Path,
    ) -> None:
        self._config = config
        self._commands_mcp = commands_mcp
        self._command_names = command_names
        self._sessions_file = sessions_file
        self._worker_dir = worker_dir

        self._sessions: dict[int, dict] = {}
        self._clients: dict[int, Any] = {}
        self._exit_stacks: dict[int, AsyncExitStack] = {}
        self._locks: dict[int, asyncio.Lock] = {}

        # Session-specific config overrides (in-memory, cleared on /reset or restart).
        self._session_overrides: dict[int, dict[str, Any]] = {}
        self._pending_override_reset: set[int] = set()
        # Set post-init by WorkerRuntime after the runner is constructed.
        self._builtins_mcp: Any = None

        self._load_sessions()

    # ------------------------------------------------------------------ #
    # Session persistence
    # ------------------------------------------------------------------ #

    def _load_sessions(self) -> None:
        """Load sessions from the JSON file on disk."""
        if self._sessions_file.exists():
            try:
                data = json.loads(self._sessions_file.read_text())
                for entry in data:
                    session = AgentSession(**entry)
                    self._sessions[session.chat_id] = {
                        "chat_id": session.chat_id,
                        "session_id": session.session_id,
                    }
            except (json.JSONDecodeError, Exception):
                logger.warning("Failed to load sessions from %s", self._sessions_file)
                self._sessions = {}
        logger.debug("Loaded %d sessions from %s", len(self._sessions), self._sessions_file)

    def _save_sessions(self) -> None:
        """Persist current sessions to disk as JSON."""
        data = [
            AgentSession(chat_id=v["chat_id"], session_id=v["session_id"]).model_dump()
            for v in self._sessions.values()
        ]
        self._sessions_file.parent.mkdir(parents=True, exist_ok=True)
        self._sessions_file.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------ #
    # Locking
    # ------------------------------------------------------------------ #

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        """Return a per-chat asyncio.Lock, creating one on first use."""
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    # ------------------------------------------------------------------ #
    # SDK message logging
    # ------------------------------------------------------------------ #

    def _log_sdk_message(self, msg: Any) -> None:
        """Emit structured log lines for each SDK message/block type."""
        from claude_agent_sdk import AssistantMessage, UserMessage, ResultMessage
        from claude_agent_sdk import ThinkingBlock, ToolUseBlock, ToolResultBlock

        if isinstance(msg, (AssistantMessage, UserMessage)):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    inp = repr(block.input)
                    logger.info("[tool_use] %s input=%s", block.name, inp[:120])
                    logger.debug("[tool_use] %s full_input=%r", block.name, block.input)
                elif isinstance(block, ToolResultBlock):
                    content = block.content
                    if isinstance(content, str):
                        length = len(content)
                    elif isinstance(content, list):
                        length = sum(len(str(c)) for c in content)
                    else:
                        length = 0
                    if block.is_error:
                        preview = str(content)[:120] if content else ""
                        logger.error("[tool_error] %s → %s", block.tool_use_id[:8], preview)
                    else:
                        logger.info("[tool_result] %s → %d chars", block.tool_use_id[:8], length)
                        logger.debug("[tool_result] %s full=%r", block.tool_use_id[:8], content)
                elif isinstance(block, ThinkingBlock):
                    logger.info("[thinking] %d chars", len(block.thinking))
                    logger.debug("[thinking] %s", block.thinking)
        elif isinstance(msg, ResultMessage):
            cost = msg.total_cost_usd
            cost_str = f"${cost:.4f}" if cost is not None else "n/a"
            logger.info(
                "[result] turns=%d cost=%s stop=%s",
                msg.num_turns, cost_str, msg.stop_reason,
            )
            if msg.usage:
                logger.debug("[result] usage=%r", msg.usage)

    # ------------------------------------------------------------------ #
    # Session overrides
    # ------------------------------------------------------------------ #

    def set_session_override(self, chat_id: int, **kwargs: Any) -> None:
        """Store per-session config overrides; client will be recreated on next turn."""
        self._session_overrides.setdefault(chat_id, {}).update(kwargs)
        self._pending_override_reset.add(chat_id)
        logger.info("Session override set for chat_id=%d: %r", chat_id, kwargs)

    def clear_session_override(self, chat_id: int) -> None:
        """Remove all session overrides for a chat."""
        self._session_overrides.pop(chat_id, None)
        self._pending_override_reset.discard(chat_id)

    def set_builtins_mcp(self, server: Any) -> None:
        """Attach the built-in MCP server after construction."""
        self._builtins_mcp = server

    # ------------------------------------------------------------------ #
    # Client management
    # ------------------------------------------------------------------ #

    async def _close_client(self, chat_id: int) -> None:
        """Close and remove the client for chat_id without wiping session data."""
        if chat_id in self._exit_stacks:
            try:
                await self._exit_stacks[chat_id].aclose()
            except Exception:
                logger.warning("Error closing client for chat_id=%d", chat_id, exc_info=True)
            del self._exit_stacks[chat_id]
        self._clients.pop(chat_id, None)

    def _build_mcp_servers(self) -> dict[str, Any]:
        """Return the MCP servers dict for ClaudeAgentOptions."""
        servers: dict[str, Any] = {}
        if self._commands_mcp is not None:
            servers["commands"] = self._commands_mcp
        if self._builtins_mcp is not None:
            servers["builtins"] = self._builtins_mcp
        return servers

    async def _get_or_create_client(self, chat_id: int) -> Any:
        """Lazily create and cache a ClaudeSDKClient for this chat_id."""
        if chat_id not in self._clients:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

            stack = AsyncExitStack()
            self._exit_stacks[chat_id] = stack

            session_id = self._sessions.get(chat_id, {}).get("session_id")
            if session_id:
                logger.info("Resuming session for chat_id=%d", chat_id)
            else:
                logger.info("Creating new client for chat_id=%d", chat_id)

            thinking_budget = getattr(self._config, "thinking_budget_tokens", None)
            base_kwargs: dict[str, Any] = {
                "system_prompt": getattr(
                    self._config,
                    "system_prompt",
                    "You are a worker agent. Your world is this folder.",
                ),
                "allowed_tools": [
                    "Read", "Write", "Bash", "Glob",
                    *self._command_names,
                    *(["set_session_config"] if self._builtins_mcp is not None else []),
                ],
                "permission_mode": "bypassPermissions",
                "cwd": str(self._worker_dir),
                "mcp_servers": self._build_mcp_servers(),
                "model": self._config.model,
                "max_turns": self._config.max_turns,
            }
            if thinking_budget is not None:
                base_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

            # Merge session-specific overrides (e.g. model, max_turns).
            overrides = dict(self._session_overrides.get(chat_id, {}))
            if "thinking_budget_tokens" in overrides:
                budget = overrides.pop("thinking_budget_tokens")
                overrides["thinking"] = {"type": "enabled", "budget_tokens": budget}
            base_kwargs.update(overrides)

            options = ClaudeAgentOptions(**base_kwargs)

            client = ClaudeSDKClient(options)
            if session_id:
                client.session_id = session_id

            await stack.enter_async_context(client)
            self._clients[chat_id] = client

        return self._clients[chat_id]

    # ------------------------------------------------------------------ #
    # Run
    # ------------------------------------------------------------------ #

    async def run(self, message: str, chat_id: int | None, worker_dir: Path) -> str:
        """Run the agent.

        Two paths:
        - chat_id is None  -> one-shot: create disposable client, run, close
        - chat_id not None -> locked, persistent session
        """
        if chat_id is None:
            return await self._run_one_shot(message)
        return await self._run_interactive(message, chat_id)

    async def _run_one_shot(self, message: str) -> str:
        """Execute a one-shot prompt with a disposable client."""
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

        thinking_budget = getattr(self._config, "thinking_budget_tokens", None)
        options = ClaudeAgentOptions(
            system_prompt=getattr(
                self._config,
                "system_prompt",
                "You are a worker agent. Your world is this folder.",
            ),
            allowed_tools=["Read", "Write", "Bash", "Glob", *self._command_names],
            permission_mode="bypassPermissions",
            cwd=str(self._worker_dir),
            mcp_servers=({"commands": self._commands_mcp} if self._commands_mcp is not None else {}),
            model=self._config.model,
            max_turns=self._config.max_turns,
            **({"thinking": {"type": "enabled", "budget_tokens": thinking_budget}}
               if thinking_budget is not None else {}),
        )

        logger.info("Agent one-shot query: %r", message[:80])
        t0 = time.monotonic()
        parts: list[str] = []
        async for msg in query(prompt=message, options=options):
            self._log_sdk_message(msg)
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        elapsed = time.monotonic() - t0
        response = "".join(parts)
        logger.info("Agent one-shot complete: %d chars in %.1fs", len(response), elapsed)
        return response

    async def _run_interactive(self, message: str, chat_id: int) -> str:
        """Execute a message within a persistent, locked session."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        lock = self._get_lock(chat_id)
        async with lock:
            # If overrides changed since last turn, close the stale client so
            # _get_or_create_client rebuilds it with the new options.
            if chat_id in self._pending_override_reset and chat_id in self._clients:
                await self._close_client(chat_id)
                self._pending_override_reset.discard(chat_id)

            logger.info("Agent query chat_id=%d: %r", chat_id, message[:80])
            t0 = time.monotonic()

            # Set ContextVar so builtin MCP tool handlers can identify this session.
            token = _current_chat_id.set(chat_id)
            try:
                client = await self._get_or_create_client(chat_id)
                await client.query(message)

                parts: list[str] = []
                async for msg in client.receive_response():
                    self._log_sdk_message(msg)
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                parts.append(block.text)
                    elif isinstance(msg, ResultMessage):
                        if msg.session_id:
                            self._sessions[chat_id] = {
                                "chat_id": chat_id,
                                "session_id": msg.session_id,
                            }
                            logger.debug("Session updated for chat_id=%d", chat_id)
            finally:
                _current_chat_id.reset(token)

            elapsed = time.monotonic() - t0
            response = "".join(parts)
            logger.info("Agent response chat_id=%d: %d chars in %.1fs", chat_id, len(response), elapsed)
            self._save_sessions()
            return response

    # ------------------------------------------------------------------ #
    # Reset / Close
    # ------------------------------------------------------------------ #

    async def reset_session(self, chat_id: int) -> None:
        """Close the client stack, clear session data and overrides, and save."""
        await self._close_client(chat_id)
        self._sessions.pop(chat_id, None)
        self._locks.pop(chat_id, None)
        self.clear_session_override(chat_id)
        self._save_sessions()

    async def close(self) -> None:
        """Close all client stacks and save sessions."""
        for stack in list(self._exit_stacks.values()):
            try:
                await stack.aclose()
            except Exception:
                logger.warning("Error closing exit stack", exc_info=True)
        self._exit_stacks.clear()
        self._clients.clear()
        self._save_sessions()
