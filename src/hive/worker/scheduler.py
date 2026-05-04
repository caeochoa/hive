"""Scheduled task runner for Workers using APScheduler."""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from hive.shared.config import WorkerConfig
from hive.shared.models import ScheduleEntry
from hive.worker.agent import AgentRunner
from hive.worker.commands import CommandError, CommandRegistry
from hive.worker.utils import md_to_telegram_html, send_long_message

logger = logging.getLogger(__name__)


class WorkerScheduler:
    """Manages cron-scheduled tasks for a single Worker."""

    def __init__(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AgentRunner,
        bot,
        allowed_user_ids: list[int],
        auto_commit: Callable[[str], Awaitable[None]],
    ) -> None:
        self._config = config
        self._registry = registry
        self._agent = agent
        self._bot = bot
        self._allowed_user_ids = allowed_user_ids
        self._auto_commit = auto_commit
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Register all schedule entries as APScheduler jobs and start."""
        for entry in self._config.schedule:
            if entry.skip_if_five_hour_above is not None or entry.skip_if_seven_day_above is not None:
                logger.warning(
                    "Schedule entry %r has skip_if thresholds configured, but usage-aware "
                    "skipping is not yet functional — the Claude Agent SDK does not expose "
                    "subscription usage percentages. The task will always run.",
                    (entry.agent_prompt or entry.run or "")[:60],
                )
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
                    args=[entry],
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
        """Execute a scheduled command, send output to Telegram, and auto-commit."""
        logger.info("Scheduled command starting: %s", meta.name)
        try:
            output = await self._registry.execute(meta, {})
            logger.info("Scheduled command complete: %s", meta.name)
            if output.strip():
                for uid in self._allowed_user_ids:
                    await send_long_message((self._bot, uid), output)
        except CommandError as e:
            logger.error("Scheduled command %s failed: %s", meta.name, e)
            try:
                for uid in self._allowed_user_ids:
                    await self._bot.send_message(
                        chat_id=uid,
                        text=f"Scheduled task <b>{html.escape(meta.name)}</b> failed:\n<pre>{html.escape(str(e))}</pre>",
                        parse_mode="HTML",
                    )
            except Exception:
                logger.exception("Failed to send error notification for command %s", meta.name)
        finally:
            await self._auto_commit("scheduled command: " + meta.name)

    async def _run_agent_prompt(self, entry: ScheduleEntry) -> None:
        """Execute a scheduled agent prompt for each allowed user and auto-commit."""
        prompt = entry.agent_prompt or ""
        logger.info("Scheduled agent prompt starting: %r", prompt[:60])

        try:
            for user_id in self._allowed_user_ids:
                response = await self._agent.run(
                    prompt, chat_id=user_id, worker_dir=self._config.worker_dir
                )
                logger.info(
                    "Scheduled agent prompt complete for user %d: %d chars",
                    user_id, len(response),
                )
                await send_long_message(
                    (self._bot, user_id),
                    md_to_telegram_html(response),
                    parse_mode="HTML",
                )
        finally:
            await self._auto_commit("scheduled agent prompt")

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Log exceptions from failed jobs and notify users via Telegram."""
        logger.error(
            "Scheduled job %s failed: %s",
            event.job_id,
            event.exception,
            exc_info=event.exception,
        )
        asyncio.get_running_loop().create_task(self._notify_job_error(event))

    async def _notify_job_error(self, event: JobExecutionEvent) -> None:
        """Send a Telegram notification for an unexpected job-level failure."""
        for uid in self._allowed_user_ids:
            await self._bot.send_message(
                chat_id=uid,
                text=f"Scheduled job <b>{html.escape(str(event.job_id))}</b> failed:\n<pre>{html.escape(str(event.exception))}</pre>",
                parse_mode="HTML",
            )
