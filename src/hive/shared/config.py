from __future__ import annotations
import tomllib
from pathlib import Path
from typing import Optional
from dotenv import dotenv_values
from pydantic import BaseModel
from hive.shared.models import ScheduleEntry, CombCell


class ConfigError(Exception):
    pass


class WorkerConfig(BaseModel):
    name: str
    worker_dir: Path
    telegram_bot_token: str
    telegram_allowed_user_id: int
    agent_model: str = "claude-haiku-4-5"
    agent_memory_dir: str = "memory/"
    agent_max_turns: int = 10
    agent_system_prompt: Optional[str] = None
    schedule: list[ScheduleEntry] = []
    comb_cells: list[CombCell] = []


def load_worker_config(worker_dir: Path) -> WorkerConfig:
    worker_dir = Path(worker_dir)
    toml_path = worker_dir / "hive.toml"
    if not toml_path.exists():
        raise ConfigError(f"hive.toml not found in {worker_dir}")

    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    # Load .env (secrets)
    env_path = worker_dir / ".env"
    env = dotenv_values(env_path) if env_path.exists() else {}

    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN not found in .env")
    allowed_id = env.get("TELEGRAM_ALLOWED_USER_ID")
    if not allowed_id:
        raise ConfigError("TELEGRAM_ALLOWED_USER_ID not found in .env")

    worker_section = raw.get("worker", {})
    agent_section = raw.get("agent", {})
    schedule_raw = raw.get("schedule", [])
    comb_raw = raw.get("comb", {}).get("cells", [])

    return WorkerConfig(
        name=worker_section["name"],
        worker_dir=worker_dir,
        telegram_bot_token=token,
        telegram_allowed_user_id=int(allowed_id),
        agent_model=agent_section.get("model", "claude-haiku-4-5"),
        agent_memory_dir=agent_section.get("memory_dir", "memory/"),
        agent_max_turns=int(agent_section.get("max_turns", 10)),
        agent_system_prompt=agent_section.get("system_prompt"),
        schedule=[ScheduleEntry(**s) for s in schedule_raw],
        comb_cells=[CombCell(**c) for c in comb_raw],
    )
