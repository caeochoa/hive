from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from hive.shared.models import WorkerEntry

DEFAULT_REGISTRY_PATH = Path.home() / ".config" / "hive" / "workers.json"


class HiveRegistry:
    def __init__(self, registry_path: Path = DEFAULT_REGISTRY_PATH):
        self._path = Path(registry_path)

    def _load(self) -> list[WorkerEntry]:
        if not self._path.exists():
            return []
        with open(self._path) as f:
            data = json.load(f)
        return [WorkerEntry(**e) for e in data]

    def _save(self, entries: list[WorkerEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump([e.model_dump() for e in entries], f, indent=2)

    def register(self, name: str, path: str) -> None:
        entries = self._load()
        entries = [e for e in entries if e.name != name]
        entries.append(WorkerEntry(name=name, path=path))
        self._save(entries)

    def unregister(self, name: str) -> None:
        entries = self._load()
        self._save([e for e in entries if e.name != name])

    def get(self, name: str) -> Optional[WorkerEntry]:
        for e in self._load():
            if e.name == name:
                return e
        return None

    def list_workers(self) -> list[WorkerEntry]:
        return self._load()
