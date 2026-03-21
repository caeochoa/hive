"""Scheduled task runner for Workers using APScheduler."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from hive.shared.config import WorkerConfig
from hive.worker.commands import CommandRegistry
from hive.worker.agent import AgentRunner
from hive.worker.utils import send_long_message, md_to_telegram_html

logger = logging.getLogger(__name__)


class WorkerScheduler:
    """Manages cron-scheduled tasks for a single Worker."""

    def __init__(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AgentRunner,
        bot,
        allowed_user_id: int,
        auto_commit: Callable[[str], Awaitable[None]],
    ) -> None:
        self._config = config
        self._registry = registry
        self._agent = agent
        self._bot = bot
        self._allowed_user_id = allowed_user_id
        self._auto_commit = auto_commit
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Register all schedule entries as APScheduler jobs and start."""
        for entry in self._config.schedule:
            trigger = CronTrigger.from_crontab(entry.cron)

            if entry.run:
                # Find matching CommandMeta by script filename
                meta = self._find_command_meta(entry.run)
                if meta is None:
                    logger.warning(
                        "Scheduled command %s not found in registry, skipping",
                        entry.run,
                    )
                    continue
                self._scheduler.add_job(
                    self._run_command,
                    trigger=trigger,
                    args=[meta],
                    name=f"cmd:{entry.run}",
                )
            elif entry.agent_prompt:
                self._scheduler.add_job(
                    self._run_agent_prompt,
                    trigger=trigger,
                    args=[entry.agent_prompt],
                    name=f"prompt:{entry.agent_prompt[:40]}",
                )

        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self._scheduler.start()

    def stop(self) -> None:
        """Shut down the scheduler without waiting for running jobs."""
        self._scheduler.shutdown(wait=False)

    def _find_command_meta(self, run_path: str):
        """Find a CommandMeta whose script_path filename matches run_path's filename."""
        target_name = Path(run_path).name
        for meta in self._registry._commands.values():
            if Path(meta.script_path).name == target_name:
                return meta
        return None

    async def _run_command(self, meta) -> None:
        """Execute a scheduled command and auto-commit."""
        try:
            await self._registry.execute(meta, {})
        finally:
            await self._auto_commit("scheduled command: " + meta.name)

    async def _run_agent_prompt(self, prompt: str) -> None:
        """Execute a scheduled agent prompt, send the response, and auto-commit."""
        try:
            response = await self._agent.run(
                prompt, chat_id=None, worker_dir=self._config.worker_dir
            )
            await send_long_message(
                (self._bot, self._allowed_user_id),
                md_to_telegram_html(response),
                parse_mode="HTML",
            )
        finally:
            await self._auto_commit("scheduled agent prompt")

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Log exceptions from failed jobs."""
        logger.error(
            "Scheduled job %s failed: %s",
            event.job_id,
            event.exception,
            exc_info=event.exception,
        )
