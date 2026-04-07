from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator


class CommandArg(BaseModel):
    name: str
    type: str  # "int", "str", "float", "bool"
    description: str
    default: str | int | float | bool | None = None

    @property
    def required(self) -> bool:
        return self.default is None


class CommandMeta(BaseModel):
    name: str
    description: str
    script_path: str
    args: list[CommandArg] = []


class ScheduleEntry(BaseModel):
    cron: str
    run: str | None = None
    agent_prompt: str | None = None
    skip_if_five_hour_above: float | None = None
    skip_if_seven_day_above: float | None = None
    notify_on_skip: bool = True

    @field_validator("skip_if_five_hour_above", "skip_if_seven_day_above", mode="before")
    @classmethod
    def validate_threshold(cls, v: object) -> object:
        if v is not None and not (0.0 <= float(v) <= 100.0):
            raise ValueError("threshold must be between 0.0 and 100.0")
        return v

    @model_validator(mode="after")
    def check_run_or_agent(self) -> ScheduleEntry:
        if self.run is None and self.agent_prompt is None:
            raise ValueError("ScheduleEntry must have either 'run' or 'agent_prompt'")
        return self


class CombCell(BaseModel):
    type: str  # "log", "file", "metric", "status", "table", "chart"
    title: str
    source: str
    key: str | None = None

    @model_validator(mode="after")
    def check_metric_key(self) -> CombCell:
        if self.type in ("metric", "status") and self.key is None:
            raise ValueError(f"CombCell of type '{self.type}' requires a 'key'")
        return self


class AgentSession(BaseModel):
    chat_id: int
    session_id: str


class WorkerEntry(BaseModel):
    name: str
    path: str
    comb_port: int | None = None
