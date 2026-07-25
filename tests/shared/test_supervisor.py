import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hive.shared.supervisor import (
    ensure_supervisord_conf,
    get_worker_conf_path,
    install_launchagent,
    install_launchdaemon,
    is_boot_config_installed,
    is_launchdaemon_installed,
    remove_worker_block,
    render_launchdaemon_plist,
    uninstall_launchagent,
    uninstall_launchdaemon,
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


# ------------------------------------------------------------------ #
# LaunchDaemon (boot mode)
# ------------------------------------------------------------------ #


@pytest.fixture
def daemon_paths(tmp_path):
    """Patch every plist/conf path constant into tmp_path; yields a namespace."""
    paths = MagicMock()
    paths.agent_plist = tmp_path / "LaunchAgents" / "com.hive.supervisord.plist"
    paths.daemon_plist = tmp_path / "LaunchDaemons" / "com.hive.supervisord.plist"
    paths.staged = tmp_path / "hive" / "com.hive.supervisord.daemon.plist"
    paths.conf = tmp_path / "hive" / "supervisord.conf"
    paths.agent_plist.parent.mkdir(parents=True)
    paths.daemon_plist.parent.mkdir(parents=True)
    with (
        patch("hive.shared.supervisor.LAUNCHAGENT_PLIST", paths.agent_plist),
        patch("hive.shared.supervisor.LAUNCHDAEMON_PLIST", paths.daemon_plist),
        patch("hive.shared.supervisor.LAUNCHDAEMON_STAGED", paths.staged),
        patch("hive.shared.supervisor.SUPERVISORD_CONF", paths.conf),
    ):
        yield paths


def test_render_launchdaemon_plist_contents(daemon_paths):
    with (
        patch("hive.shared.supervisor.shutil.which", return_value="/opt/homebrew/bin/supervisord"),
        patch("hive.shared.supervisor.getpass.getuser", return_value="alice"),
        patch.dict("os.environ", {"PATH": "/opt/homebrew/bin:/usr/bin"}, clear=False),
    ):
        content = render_launchdaemon_plist()
    assert "<string>com.hive.supervisord</string>" in content
    assert "<string>/opt/homebrew/bin/supervisord</string>" in content
    assert str(daemon_paths.conf) in content
    assert "<key>UserName</key>" in content
    assert "<string>alice</string>" in content
    assert "<key>HOME</key>" in content
    assert "<key>USER</key>" in content
    assert "<key>LOGNAME</key>" in content
    assert "<key>PATH</key>" in content
    assert "/opt/homebrew/bin:/usr/bin" in content
    assert "<key>RunAtLoad</key>" in content
    assert "<key>KeepAlive</key>" in content
    assert "<key>StandardOutPath</key>" in content


def test_render_launchdaemon_plist_requires_supervisord(daemon_paths):
    with patch("hive.shared.supervisor.shutil.which", return_value=None):
        with pytest.raises(RuntimeError):
            render_launchdaemon_plist()


def test_is_launchdaemon_installed(daemon_paths):
    assert not is_launchdaemon_installed()
    daemon_paths.daemon_plist.write_text("<plist/>")
    assert is_launchdaemon_installed()


def test_is_boot_config_installed_daemon_only(daemon_paths):
    daemon_paths.daemon_plist.write_text("<plist/>")
    assert is_boot_config_installed()


def test_is_boot_config_installed_agent_only(daemon_paths):
    daemon_paths.agent_plist.write_text("<plist/>")
    with patch("hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=0)):
        assert is_boot_config_installed()


def test_is_boot_config_installed_neither(daemon_paths):
    with patch("hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=1)):
        assert not is_boot_config_installed()


def test_uninstall_launchagent_removes_plist(daemon_paths):
    daemon_paths.agent_plist.write_text("<plist/>")
    with patch(
        "hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=0)
    ) as mock_run:
        uninstall_launchagent()
    assert not daemon_paths.agent_plist.exists()
    first_cmd = mock_run.call_args_list[0].args[0]
    assert first_cmd[:2] == ["launchctl", "bootout"]
    assert first_cmd[2].endswith("/com.hive.supervisord")


def test_install_launchdaemon_command_sequence(daemon_paths):
    daemon_paths.agent_plist.write_text("<plist/>")
    sudo_calls = []

    def run_sudo(args):
        sudo_calls.append(args)
        return MagicMock(returncode=0)

    with (
        patch("hive.shared.supervisor.shutil.which", return_value="/opt/homebrew/bin/supervisord"),
        patch("hive.shared.supervisor.getpass.getuser", return_value="alice"),
        patch("hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        install_launchdaemon(run_sudo)

    # Staged plist written with rendered content; LaunchAgent migrated away
    assert daemon_paths.staged.exists()
    assert "<key>UserName</key>" in daemon_paths.staged.read_text()
    assert not daemon_paths.agent_plist.exists()

    # sudo sequence: bootout -> install(root:wheel 644) -> bootstrap -> enable
    assert sudo_calls[0] == ["launchctl", "bootout", "system/com.hive.supervisord"]
    assert sudo_calls[1] == [
        "install", "-o", "root", "-g", "wheel", "-m", "644",
        str(daemon_paths.staged), str(daemon_paths.daemon_plist),
    ]
    assert sudo_calls[2] == ["launchctl", "bootstrap", "system", str(daemon_paths.daemon_plist)]
    assert sudo_calls[3] == ["launchctl", "enable", "system/com.hive.supervisord"]


def test_install_launchdaemon_raises_when_bootstrap_fails(daemon_paths):
    def run_sudo(args):
        failing = args[:2] in (["launchctl", "bootstrap"], ["launchctl", "load"])
        return MagicMock(returncode=1 if failing else 0)

    with (
        patch("hive.shared.supervisor.shutil.which", return_value="/opt/homebrew/bin/supervisord"),
        patch("hive.shared.supervisor.getpass.getuser", return_value="alice"),
        patch("hive.shared.supervisor.subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        with pytest.raises(RuntimeError):
            install_launchdaemon(run_sudo)


def test_uninstall_launchdaemon_commands(daemon_paths):
    sudo_calls = []

    def run_sudo(args):
        sudo_calls.append(args)
        return MagicMock(returncode=0)

    uninstall_launchdaemon(run_sudo)

    assert sudo_calls[0] == ["launchctl", "bootout", "system/com.hive.supervisord"]
    assert sudo_calls[1] == ["rm", "-f", str(daemon_paths.daemon_plist)]


def test_wait_for_supervisord_exit_returns_when_no_pidfile(daemon_paths):
    from hive.shared.supervisor import _wait_for_supervisord_exit

    # No pidfile next to SUPERVISORD_CONF -> returns immediately (well under timeout)
    _wait_for_supervisord_exit(timeout=0.2)
