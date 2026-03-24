import pytest
from pathlib import Path
from hive.shared.config import load_worker_config, ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_config():
    config = load_worker_config(FIXTURES / "valid")
    assert config.name == "budget"
    assert config.telegram_bot_token == "test-token-123"
    assert config.telegram_allowed_user_ids == [999888]


def test_load_agent_config():
    config = load_worker_config(FIXTURES / "valid")
    assert config.agent_model == "claude-haiku-4-5"
    assert config.agent_max_turns == 10
    assert config.agent_memory_dir == "memory/"


def test_load_schedule():
    config = load_worker_config(FIXTURES / "valid")
    assert len(config.schedule) == 1
    assert config.schedule[0].cron == "0 8 * * *"
    assert config.schedule[0].run == "commands/morning.py"


def test_load_comb_cells():
    config = load_worker_config(FIXTURES / "valid")
    assert len(config.comb_cells) == 2
    assert config.comb_cells[0].type == "log"
    assert config.comb_cells[1].type == "metric"
    assert config.comb_cells[1].key == "tasks_today"


def test_minimal_config_defaults():
    # Tested via test_minimal_config_with_env which provides required secrets
    pass


def test_missing_toml_raises():
    with pytest.raises(ConfigError, match="hive.toml"):
        load_worker_config(Path("/nonexistent/path"))


def test_missing_token_raises():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_worker_config(FIXTURES / "minimal")  # no .env with token


def test_minimal_config_with_env(tmp_path):
    (tmp_path / "hive.toml").write_text('[worker]\nname = "minimal"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.name == "minimal"
    assert config.schedule == []
    assert config.comb_cells == []
    assert config.agent_model == "claude-haiku-4-5"
    assert config.agent_max_turns == 10


def test_thinking_budget_tokens_default(tmp_path):
    """agent_thinking_budget_tokens defaults to None when not set."""
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_thinking_budget_tokens is None


def test_thinking_budget_tokens_from_toml(tmp_path):
    """agent_thinking_budget_tokens is parsed from [agent] section."""
    (tmp_path / "hive.toml").write_text(
        '[worker]\nname = "t"\n[agent]\nthinking_budget_tokens = 5000\n'
    )
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_thinking_budget_tokens == 5000
