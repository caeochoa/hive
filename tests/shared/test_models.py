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
