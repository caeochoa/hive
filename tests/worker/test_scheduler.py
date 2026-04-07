"""Tests for hive.worker.scheduler module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.shared.config import WorkerConfig
from hive.shared.models import CommandMeta, ScheduleEntry
from hive.worker.commands import CommandRegistry
from hive.worker.scheduler import WorkerScheduler
from hive.worker.usage import UsageStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def worker_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def config(worker_dir: Path) -> WorkerConfig:
    return WorkerConfig(
        name="test-worker",
        worker_dir=worker_dir,
        telegram_bot_token="fake-token",
        telegram_allowed_user_ids=[12345],
        schedule=[
            ScheduleEntry(cron="0 8 * * *", run="commands/morning_brief.py"),
            ScheduleEntry(
                cron="0 9 * * 1",
                agent_prompt="Prepare the weekly summary",
            ),
        ],
    )


@pytest.fixture
def registry(config: WorkerConfig) -> CommandRegistry:
    reg = CommandRegistry(config)
    # Manually inject a command so the scheduler can find it
    meta = CommandMeta(
        name="morning_brief",
        description="Morning briefing",
        script_path=str(config.worker_dir / "commands" / "morning_brief.py"),
    )
    reg._commands["morning_brief"] = meta
    return reg


@pytest.fixture
def agent() -> AsyncMock:
    agent = AsyncMock()
    agent.run = AsyncMock(return_value="Agent response text")
    return agent


@pytest.fixture
def bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def auto_commit() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def scheduler(
    config: WorkerConfig,
    registry: CommandRegistry,
    agent: AsyncMock,
    bot: AsyncMock,
    auto_commit: AsyncMock,
) -> WorkerScheduler:
    return WorkerScheduler(
        config=config,
        registry=registry,
        agent=agent,
        bot=bot,
        allowed_user_ids=[12345],
        auto_commit=auto_commit,
    )


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


class TestStart:
    async def test_adds_correct_number_of_jobs(self, scheduler: WorkerScheduler) -> None:
        scheduler.start()
        jobs = scheduler._scheduler.get_jobs()
        # One command job + one agent prompt job
        assert len(jobs) == 2
        scheduler.stop()

    async def test_skips_missing_command(
        self,
        config: WorkerConfig,
        agent: AsyncMock,
        bot: AsyncMock,
        auto_commit: AsyncMock,
    ) -> None:
        # Empty registry - no commands discovered
        empty_reg = CommandRegistry(config)
        sched = WorkerScheduler(
            config=config,
            registry=empty_reg,
            agent=agent,
            bot=bot,
            allowed_user_ids=[12345],
            auto_commit=auto_commit,
        )
        sched.start()
        jobs = sched._scheduler.get_jobs()
        # Only the agent prompt job should be added
        assert len(jobs) == 1
        sched.stop()


class TestStop:
    async def test_stop_calls_shutdown(self, scheduler: WorkerScheduler) -> None:
        scheduler.start()
        with patch.object(scheduler._scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()
            mock_shutdown.assert_called_once_with(wait=False)


# ---------------------------------------------------------------------------
# _run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    async def test_run_command_executes_and_auto_commits(
        self,
        scheduler: WorkerScheduler,
        registry: CommandRegistry,
        auto_commit: AsyncMock,
    ) -> None:
        meta = list(registry._commands.values())[0]

        with patch.object(registry, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "output"
            await scheduler._run_command(meta)

        mock_exec.assert_awaited_once_with(meta, {})
        auto_commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# _run_agent_prompt
# ---------------------------------------------------------------------------


class TestRunAgentPrompt:
    async def test_run_agent_prompt_calls_agent_and_sends_message(
        self,
        scheduler: WorkerScheduler,
        agent: AsyncMock,
        bot: AsyncMock,
        auto_commit: AsyncMock,
        config: WorkerConfig,
    ) -> None:
        entry = ScheduleEntry(cron="0 9 * * 1", agent_prompt="Do the thing")
        await scheduler._run_agent_prompt(entry)

        agent.run.assert_awaited_once_with(
            "Do the thing", chat_id=12345, worker_dir=config.worker_dir
        )
        bot.send_message.assert_awaited_once_with(
            chat_id=12345, text="Agent response text", parse_mode="HTML"
        )
        auto_commit.assert_awaited_once()

    async def test_no_usage_store_always_runs(
        self,
        scheduler: WorkerScheduler,
        agent: AsyncMock,
    ) -> None:
        """Scheduler without a UsageStore always runs the task."""
        assert scheduler._usage_store is None
        entry = ScheduleEntry(
            cron="0 9 * * 1",
            agent_prompt="Do the thing",
            skip_if_five_hour_above=10.0,
        )
        await scheduler._run_agent_prompt(entry)
        agent.run.assert_awaited_once()

    async def test_skips_and_notifies_when_limit_exceeded(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AsyncMock,
        bot: AsyncMock,
        auto_commit: AsyncMock,
        tmp_path: Path,
    ) -> None:
        usage_store = MagicMock(spec=UsageStore)
        usage_store.check_limits.return_value = (False, "5-hour usage 85.0% >= threshold 80.0%")

        sched = WorkerScheduler(
            config=config,
            registry=registry,
            agent=agent,
            bot=bot,
            allowed_user_ids=[12345],
            auto_commit=auto_commit,
            usage_store=usage_store,
        )
        entry = ScheduleEntry(
            cron="0 9 * * 1",
            agent_prompt="Do the thing",
            skip_if_five_hour_above=80.0,
            notify_on_skip=True,
        )
        await sched._run_agent_prompt(entry)

        agent.run.assert_not_awaited()
        bot.send_message.assert_awaited_once_with(
            chat_id=12345,
            text="Scheduled task skipped: 5-hour usage 85.0% >= threshold 80.0%",
        )

    async def test_skips_silently_when_notify_off(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AsyncMock,
        bot: AsyncMock,
        auto_commit: AsyncMock,
    ) -> None:
        usage_store = MagicMock(spec=UsageStore)
        usage_store.check_limits.return_value = (False, "7-day usage 92.0% >= threshold 90.0%")

        sched = WorkerScheduler(
            config=config,
            registry=registry,
            agent=agent,
            bot=bot,
            allowed_user_ids=[12345],
            auto_commit=auto_commit,
            usage_store=usage_store,
        )
        entry = ScheduleEntry(
            cron="0 9 * * 1",
            agent_prompt="Do the thing",
            skip_if_seven_day_above=90.0,
            notify_on_skip=False,
        )
        await sched._run_agent_prompt(entry)

        agent.run.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    async def test_runs_when_within_limits(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AsyncMock,
        bot: AsyncMock,
        auto_commit: AsyncMock,
    ) -> None:
        usage_store = MagicMock(spec=UsageStore)
        usage_store.check_limits.return_value = (True, None)

        sched = WorkerScheduler(
            config=config,
            registry=registry,
            agent=agent,
            bot=bot,
            allowed_user_ids=[12345],
            auto_commit=auto_commit,
            usage_store=usage_store,
        )
        entry = ScheduleEntry(
            cron="0 9 * * 1",
            agent_prompt="Do the thing",
            skip_if_five_hour_above=80.0,
        )
        await sched._run_agent_prompt(entry)
        agent.run.assert_awaited_once()

    async def test_no_thresholds_skips_check(
        self,
        config: WorkerConfig,
        registry: CommandRegistry,
        agent: AsyncMock,
        bot: AsyncMock,
        auto_commit: AsyncMock,
    ) -> None:
        """UsageStore.check_limits is not called when no thresholds are configured."""
        usage_store = MagicMock(spec=UsageStore)

        sched = WorkerScheduler(
            config=config,
            registry=registry,
            agent=agent,
            bot=bot,
            allowed_user_ids=[12345],
            auto_commit=auto_commit,
            usage_store=usage_store,
        )
        entry = ScheduleEntry(cron="0 9 * * 1", agent_prompt="Do the thing")
        await sched._run_agent_prompt(entry)

        usage_store.check_limits.assert_not_called()
        agent.run.assert_awaited_once()
