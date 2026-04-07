import pytest
from hive.shared.models import CommandArg, CommandMeta, ScheduleEntry, CombCell, AgentSession, WorkerEntry


def test_command_arg_defaults():
    arg = CommandArg(name="n", type="int", description="count")
    assert arg.default is None
    assert arg.required is True


def test_command_arg_with_default_is_not_required():
    arg = CommandArg(name="n", type="int", description="count", default=10)
    assert arg.required is False


def test_command_meta_minimal():
    meta = CommandMeta(name="summarise", description="Summarise logs", script_path="/worker/commands/summarise.py")
    assert meta.args == []


def test_schedule_entry_script():
    entry = ScheduleEntry(cron="0 8 * * *", run="commands/morning.py")
    assert entry.agent_prompt is None


def test_schedule_entry_agent():
    entry = ScheduleEntry(cron="0 9 * * 1", agent_prompt="Write weekly summary")
    assert entry.run is None


def test_schedule_entry_requires_run_or_agent():
    with pytest.raises(ValueError):
        ScheduleEntry(cron="0 8 * * *")  # neither run nor agent_prompt


def test_comb_cell_log():
    cell = CombCell(type="log", title="Activity", source="logs/worker.log")
    assert cell.key is None


def test_comb_cell_metric_requires_key():
    with pytest.raises(ValueError):
        CombCell(type="metric", title="Tasks", source="memory/stats.json")  # missing key


def test_agent_session():
    session = AgentSession(chat_id=123456, session_id="sess-abc")
    assert session.chat_id == 123456


def test_worker_entry():
    entry = WorkerEntry(name="budget", path="/home/user/budget")
    assert entry.name == "budget"


def test_schedule_entry_usage_limit_defaults():
    entry = ScheduleEntry(cron="0 8 * * *", agent_prompt="Do thing")
    assert entry.skip_if_five_hour_above is None
    assert entry.skip_if_seven_day_above is None
    assert entry.notify_on_skip is True


def test_schedule_entry_usage_limits_set():
    entry = ScheduleEntry(
        cron="0 8 * * *",
        agent_prompt="Do thing",
        skip_if_five_hour_above=80.0,
        skip_if_seven_day_above=90.0,
        notify_on_skip=False,
    )
    assert entry.skip_if_five_hour_above == 80.0
    assert entry.skip_if_seven_day_above == 90.0
    assert entry.notify_on_skip is False


def test_schedule_entry_usage_limits_from_dict():
    data = {
        "cron": "0 8 * * *",
        "agent_prompt": "Do thing",
        "skip_if_five_hour_above": 75.5,
    }
    entry = ScheduleEntry(**data)
    assert entry.skip_if_five_hour_above == 75.5
    assert entry.skip_if_seven_day_above is None
