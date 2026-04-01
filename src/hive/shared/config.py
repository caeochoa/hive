from __future__ import annotations

import tomllib
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel

from hive.shared.models import CombCell, ScheduleEntry


class ConfigError(Exception):
    pass


class WorkerConfig(BaseModel):
    name: str
    worker_dir: Path
    telegram_bot_token: str
    telegram_allowed_user_ids: list[int]
    agent_model: str = "claude-haiku-4-5"
    agent_memory_dir: str = "memory/"
    agent_max_turns: int = 10
    agent_system_prompt: str | None = None
    agent_thinking_budget_tokens: int | None = None
    schedule: list[ScheduleEntry] = []
    comb_cells: list[CombCell] = []
    comb_theme: str = "terminal-dark"


def _parse_allowed_ids(raw: str) -> list[int]:
    """Parse 'id1,id2,...' or a single 'id' into a list[int]."""
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_worker_toml(worker_dir: Path) -> tuple[dict[str, str], dict, dict, list, list, str]:
    """Shared TOML/env parsing used by both load functions.

    Returns (env, worker_section, agent_section, schedule_raw, comb_raw, comb_theme).
    """
    toml_path = worker_dir / "hive.toml"
    if not toml_path.exists():
        raise ConfigError(f"hive.toml not found in {worker_dir}")

    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    env_path = worker_dir / ".env"
    env = dotenv_values(env_path) if env_path.exists() else {}

    worker_section = raw.get("worker", {})
    agent_section = raw.get("agent", {})
    schedule_raw = raw.get("schedule", [])
    comb_section = raw.get("comb", {})
    comb_raw = comb_section.get("cells", [])
    comb_theme = comb_section.get("theme", "terminal-dark")

    return env, worker_section, agent_section, schedule_raw, comb_raw, comb_theme


def _build_worker_config(
    worker_dir: Path,
    token: str,
    allowed_ids: list[int],
    worker_section: dict,
    agent_section: dict,
    schedule_raw: list,
    comb_raw: list,
    comb_theme: str,
) -> WorkerConfig:
    return WorkerConfig(
        name=worker_section["name"],
        worker_dir=worker_dir,
        telegram_bot_token=token,
        telegram_allowed_user_ids=allowed_ids,
        agent_model=agent_section.get("model", "claude-haiku-4-5"),
        agent_memory_dir=agent_section.get("memory_dir", "memory/"),
        agent_max_turns=int(agent_section.get("max_turns", 10)),
        agent_system_prompt=agent_section.get("system_prompt"),
        agent_thinking_budget_tokens=agent_section.get("thinking_budget_tokens"),
        schedule=[ScheduleEntry(**s) for s in schedule_raw],
        comb_cells=[CombCell(**c) for c in comb_raw],
        comb_theme=comb_theme,
    )


def load_worker_config_for_tui(worker_dir: Path) -> WorkerConfig:
    """Like load_worker_config but skips Telegram key validation.

    TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID are optional; missing
    values are replaced with safe defaults so `hive chat` works without a
    configured Telegram bot.
    """
    worker_dir = Path(worker_dir)
    env, worker_section, agent_section, schedule_raw, comb_raw, comb_theme = (
        _parse_worker_toml(worker_dir)
    )

    token = env.get("TELEGRAM_BOT_TOKEN") or ""
    allowed_id = env.get("TELEGRAM_ALLOWED_USER_ID") or ""
    allowed_ids = _parse_allowed_ids(allowed_id) if allowed_id else []

    return _build_worker_config(
        worker_dir, token, allowed_ids,
        worker_section, agent_section, schedule_raw, comb_raw, comb_theme,
    )


def load_worker_config(worker_dir: Path) -> WorkerConfig:
    worker_dir = Path(worker_dir)
    env, worker_section, agent_section, schedule_raw, comb_raw, comb_theme = (
        _parse_worker_toml(worker_dir)
    )

    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN not found in .env")
    allowed_id = env.get("TELEGRAM_ALLOWED_USER_ID")
    if not allowed_id:
        raise ConfigError("TELEGRAM_ALLOWED_USER_ID not found in .env")

    return _build_worker_config(
        worker_dir, token, _parse_allowed_ids(allowed_id),
        worker_section, agent_section, schedule_raw, comb_raw, comb_theme,
    )
