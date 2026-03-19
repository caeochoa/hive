"""Agent runner abstraction and Claude Agent SDK implementation."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from hive.shared.models import AgentSession

logger = logging.getLogger(__name__)


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
    # Client management
    # ------------------------------------------------------------------ #

    async def _get_or_create_client(self, chat_id: int) -> Any:
        """Lazily create and cache a ClaudeSDKClient for this chat_id."""
        if chat_id not in self._clients:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

            stack = AsyncExitStack()
            self._exit_stacks[chat_id] = stack

            session_id = self._sessions.get(chat_id, {}).get("session_id")

            options = ClaudeAgentOptions(
                system_prompt=getattr(
                    self._config,
                    "system_prompt",
                    "You are a worker agent. Your world is this folder.",
                ),
                allowed_tools=["Read", "Write", "Bash", "Glob", *self._command_names],
                permission_mode="acceptEdits",
                cwd=str(self._worker_dir),
                mcp_servers=({"commands": self._commands_mcp} if self._commands_mcp is not None else {}),
                model=self._config.model,
                max_turns=self._config.max_turns,
            )

            client = ClaudeSDKClient(options)
            if session_id:
                client.session_id = session_id

            await stack.enter_async_context(client)
            self._clients[chat_id] = client

        return self._clients[chat_id]

    async def _create_one_shot_client(self) -> tuple[Any, AsyncExitStack]:
        """Create a disposable client for scheduled / one-shot prompts."""
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        stack = AsyncExitStack()

        options = ClaudeAgentOptions(
            system_prompt=getattr(
                self._config,
                "system_prompt",
                "You are a worker agent. Your world is this folder.",
            ),
            allowed_tools=["Read", "Write", "Bash", "Glob", *self._command_names],
            permission_mode="acceptEdits",
            cwd=str(self._worker_dir),
            mcp_servers=({"commands": self._commands_mcp} if self._commands_mcp is not None else {}),
            model=self._config.model,
            max_turns=self._config.max_turns,
        )

        client = ClaudeSDKClient(options)
        await stack.enter_async_context(client)
        return client, stack

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
        from claude_agent_sdk import query

        client, stack = await self._create_one_shot_client()
        try:
            result = await query(client=client, prompt=message)
            return result.response
        finally:
            await stack.aclose()

    async def _run_interactive(self, message: str, chat_id: int) -> str:
        """Execute a message within a persistent, locked session."""
        from claude_agent_sdk import query

        lock = self._get_lock(chat_id)
        async with lock:
            client = await self._get_or_create_client(chat_id)
            result = await query(client=client, prompt=message)

            # Persist session_id from the client
            self._sessions[chat_id] = {
                "chat_id": chat_id,
                "session_id": getattr(client, "session_id", ""),
            }
            self._save_sessions()

            return result.response

    # ------------------------------------------------------------------ #
    # Reset / Close
    # ------------------------------------------------------------------ #

    async def reset_session(self, chat_id: int) -> None:
        """Close the client stack, clear session data, and save."""
        if chat_id in self._exit_stacks:
            await self._exit_stacks[chat_id].aclose()
            del self._exit_stacks[chat_id]
        self._clients.pop(chat_id, None)
        self._sessions.pop(chat_id, None)
        self._locks.pop(chat_id, None)
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
