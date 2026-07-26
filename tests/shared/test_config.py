import pytest
from pathlib import Path

import hive.shared.config
from hive.shared.config import load_worker_config, load_worker_config_for_tui, ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_global_env(tmp_path, monkeypatch):
    """Keep tests independent of the developer's real ~/.config/hive/.env."""
    path = tmp_path / "global.env"
    monkeypatch.setattr(hive.shared.config, "GLOBAL_ENV_PATH", path)
    return path


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


def test_agent_env_empty_by_default(tmp_path):
    """agent_env is empty when .env has no auth keys."""
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_env == {}


def test_agent_env_forwards_auth_keys_only(tmp_path):
    """Auth keys land in agent_env; Telegram secrets do not."""
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=tok\n"
        "TELEGRAM_ALLOWED_USER_ID=1\n"
        "CLAUDE_CODE_OAUTH_TOKEN=oat-123\n"
        "ANTHROPIC_API_KEY=sk-456\n"
    )
    config = load_worker_config(tmp_path)
    assert config.agent_env == {
        "CLAUDE_CODE_OAUTH_TOKEN": "oat-123",
        "ANTHROPIC_API_KEY": "sk-456",
    }


def test_agent_env_in_tui_config(tmp_path):
    """The TUI loader forwards auth keys too."""
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text("CLAUDE_CODE_OAUTH_TOKEN=oat-123\n")
    config = load_worker_config_for_tui(tmp_path)
    assert config.agent_env == {"CLAUDE_CODE_OAUTH_TOKEN": "oat-123"}


def test_agent_env_falls_back_to_global(tmp_path, isolated_global_env):
    """Auth keys in the global Hive .env apply when the worker .env has none."""
    isolated_global_env.write_text("CLAUDE_CODE_OAUTH_TOKEN=global-oat\n")
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_env == {"CLAUDE_CODE_OAUTH_TOKEN": "global-oat"}


def test_agent_env_worker_overrides_global(tmp_path, isolated_global_env):
    """A worker's own .env auth key wins over the global one."""
    isolated_global_env.write_text("CLAUDE_CODE_OAUTH_TOKEN=global-oat\n")
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=tok\n"
        "TELEGRAM_ALLOWED_USER_ID=1\n"
        "CLAUDE_CODE_OAUTH_TOKEN=worker-oat\n"
    )
    config = load_worker_config(tmp_path)
    assert config.agent_env == {"CLAUDE_CODE_OAUTH_TOKEN": "worker-oat"}


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


# ---------------------------------------------------------------------------
# load_worker_config_for_tui
# ---------------------------------------------------------------------------


def test_tui_config_works_without_telegram_keys(tmp_path):
    """TUI config loader works when .env has no Telegram keys."""
    (tmp_path / "hive.toml").write_text('[worker]\nname = "tui-test"\n')
    config = load_worker_config_for_tui(tmp_path)
    assert config.name == "tui-test"
    assert config.telegram_bot_token == ""
    assert config.telegram_allowed_user_ids == []


def test_tui_and_full_config_identical_with_telegram_keys(tmp_path):
    """Both loaders return identical results when Telegram keys are present."""
    (tmp_path / "hive.toml").write_text('[worker]\nname = "both"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=42\n")
    full = load_worker_config(tmp_path)
    tui = load_worker_config_for_tui(tmp_path)
    assert full.name == tui.name
    assert full.telegram_bot_token == tui.telegram_bot_token
    assert full.telegram_allowed_user_ids == tui.telegram_allowed_user_ids
    assert full.agent_model == tui.agent_model
    assert full.agent_max_turns == tui.agent_max_turns


def test_tool_verbosity_defaults_to_none(tmp_path):
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_tool_verbosity == "none"


def test_show_thinking_defaults_to_false(tmp_path):
    (tmp_path / "hive.toml").write_text('[worker]\nname = "t"\n')
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_show_thinking is False


def test_tool_verbosity_from_toml(tmp_path):
    (tmp_path / "hive.toml").write_text(
        '[worker]\nname = "t"\n[agent]\ntool_verbosity = "verbose"\n'
    )
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_tool_verbosity == "verbose"


def test_show_thinking_from_toml(tmp_path):
    (tmp_path / "hive.toml").write_text(
        '[worker]\nname = "t"\n[agent]\nshow_thinking = true\n'
    )
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n")
    config = load_worker_config(tmp_path)
    assert config.agent_show_thinking is True
