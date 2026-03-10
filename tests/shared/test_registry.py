import pytest
from pathlib import Path
from hive.shared.registry import HiveRegistry
from hive.shared.models import WorkerEntry


@pytest.fixture
def registry(tmp_path):
    return HiveRegistry(registry_path=tmp_path / "workers.json")


def test_register_new_worker(registry):
    registry.register("budget", "/home/user/budget")
    entries = registry.list_workers()
    assert len(entries) == 1
    assert entries[0].name == "budget"
    assert entries[0].path == "/home/user/budget"


def test_register_idempotent(registry):
    registry.register("budget", "/home/user/budget")
    registry.register("budget", "/home/user/budget")
    assert len(registry.list_workers()) == 1


def test_unregister_worker(registry):
    registry.register("budget", "/home/user/budget")
    registry.unregister("budget")
    assert registry.list_workers() == []


def test_unregister_nonexistent_is_noop(registry):
    registry.unregister("nonexistent")  # should not raise


def test_get_worker(registry):
    registry.register("budget", "/home/user/budget")
    entry = registry.get("budget")
    assert entry is not None
    assert entry.name == "budget"


def test_get_nonexistent_returns_none(registry):
    assert registry.get("missing") is None


def test_persists_to_disk(tmp_path):
    path = tmp_path / "workers.json"
    r1 = HiveRegistry(registry_path=path)
    r1.register("budget", "/home/user/budget")

    r2 = HiveRegistry(registry_path=path)
    assert len(r2.list_workers()) == 1
