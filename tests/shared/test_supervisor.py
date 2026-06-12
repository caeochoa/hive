import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hive.shared.supervisor import (
    ensure_supervisord_conf,
    get_worker_conf_path,
    install_launchagent,
    remove_worker_block,
    write_comb_block,
    write_worker_block,
)


@pytest.fixture
def conf_dir(tmp_path):
    d = tmp_path / "conf.d"
    d.mkdir()
    return d


def test_write_worker_block(conf_dir):
    with patch("hive.shared.supervisor.shutil.which", return_value="/usr/local/bin/hive"):
        write_worker_block(
            name="budget",
            worker_path=Path("/home/user/budget"),
            conf_dir=conf_dir,
        )
    conf_file = conf_dir / "worker-budget.conf"
    assert conf_file.exists()
    content = conf_file.read_text()
    assert "[program:worker-budget]" in content
    assert "/usr/local/bin/hive run /home/user/budget" in content
    assert "autorestart=true" in content
    assert "stdout_logfile=/home/user/budget/logs/out.log" in content


def test_write_worker_block_uses_absolute_hive_path(conf_dir):
    with patch("hive.shared.supervisor.shutil.which", return_value="/usr/local/bin/hive"):
        write_worker_block("budget", Path("/home/user/budget"), conf_dir=conf_dir)
    content = (conf_dir / "worker-budget.conf").read_text()
    assert "command=/usr/local/bin/hive run /home/user/budget" in content
    assert "command=hive run" not in content


def test_write_comb_block_uses_absolute_hive_path(tmp_path):
    conf_dir = tmp_path / "conf.d"
    conf_dir.mkdir()
    with patch("hive.shared.supervisor.shutil.which", return_value="/usr/local/bin/hive"):
        write_comb_block(conf_dir=conf_dir)
    content = (conf_dir / "hive-comb.conf").read_text()
    assert "command=/usr/local/bin/hive comb serve" in content
    assert "command=hive comb" not in content


def test_ensure_supervisord_conf_migrates_nodaemon_false(tmp_path):
    conf_file = tmp_path / "supervisord.conf"
    conf_file.write_text("[supervisord]\nnodaemon=false\nlogfile=/tmp/x.log\n")
    with patch("hive.shared.supervisor.SUPERVISORD_CONF", conf_file):
        ensure_supervisord_conf()
    content = conf_file.read_text()
    assert "nodaemon=true" in content
    assert "nodaemon=false" not in content


def test_new_supervisord_conf_uses_nodaemon_true(tmp_path):
    conf_file = tmp_path / "supervisord.conf"
    with patch("hive.shared.supervisor.SUPERVISORD_CONF", conf_file):
        ensure_supervisord_conf()
    assert "nodaemon=true" in conf_file.read_text()
    assert "nodaemon=false" not in conf_file.read_text()


def test_install_launchagent_includes_path_in_plist(tmp_path):
    plist_path = tmp_path / "com.hive.supervisord.plist"
    conf_path = tmp_path / "supervisord.conf"
    with (
        patch("hive.shared.supervisor.LAUNCHAGENT_PLIST", plist_path),
        patch("hive.shared.supervisor.SUPERVISORD_CONF", conf_path),
        patch("hive.shared.supervisor.shutil.which", return_value="/opt/homebrew/bin/supervisord"),
        patch("hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=0)),
        patch.dict("os.environ", {"PATH": "/usr/local/bin:/usr/bin"}, clear=False),
    ):
        install_launchagent()
    content = plist_path.read_text()
    assert "EnvironmentVariables" in content
    assert "<key>PATH</key>" in content
    assert "/usr/local/bin:/usr/bin" in content


def test_install_launchagent_migrates_existing_plist_missing_env(tmp_path):
    plist_path = tmp_path / "com.hive.supervisord.plist"
    plist_path.write_text(
        '<?xml version="1.0"?>\n<plist version="1.0"><dict>'
        "<key>Label</key><string>com.hive.supervisord</string>"
        "</dict></plist>"
    )
    conf_path = tmp_path / "supervisord.conf"
    with (
        patch("hive.shared.supervisor.LAUNCHAGENT_PLIST", plist_path),
        patch("hive.shared.supervisor.SUPERVISORD_CONF", conf_path),
        patch("hive.shared.supervisor.shutil.which", return_value="/opt/homebrew/bin/supervisord"),
        patch("hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=0)),
        patch.dict("os.environ", {"PATH": "/usr/local/bin"}, clear=False),
    ):
        install_launchagent()
    assert "EnvironmentVariables" in plist_path.read_text()


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
