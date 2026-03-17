import pytest
from pathlib import Path
from hive.shared.supervisor import (
    write_worker_block,
    remove_worker_block,
    get_worker_conf_path,
)


@pytest.fixture
def conf_dir(tmp_path):
    d = tmp_path / "conf.d"
    d.mkdir()
    return d


def test_write_worker_block(conf_dir):
    write_worker_block(
        name="budget",
        worker_path=Path("/home/user/budget"),
        conf_dir=conf_dir,
    )
    conf_file = conf_dir / "worker-budget.conf"
    assert conf_file.exists()
    content = conf_file.read_text()
    assert "[program:worker-budget]" in content
    assert "hive run /home/user/budget" in content
    assert "autorestart=true" in content
    assert "stdout_logfile=/home/user/budget/logs/out.log" in content


def test_write_worker_block_idempotent(conf_dir):
    write_worker_block("budget", Path("/home/user/budget"), conf_dir=conf_dir)
    write_worker_block("budget", Path("/home/user/budget"), conf_dir=conf_dir)
    files = list(conf_dir.glob("*.conf"))
    assert len(files) == 1


def test_remove_worker_block(conf_dir):
    write_worker_block("budget", Path("/home/user/budget"), conf_dir=conf_dir)
    remove_worker_block("budget", conf_dir=conf_dir)
    assert not (conf_dir / "worker-budget.conf").exists()


def test_remove_nonexistent_is_noop(conf_dir):
    remove_worker_block("nonexistent", conf_dir=conf_dir)  # should not raise


def test_get_worker_conf_path(conf_dir):
    path = get_worker_conf_path("budget", conf_dir=conf_dir)
    assert path.name == "worker-budget.conf"
