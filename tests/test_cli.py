"""Tests for the Hive CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hive.cli.app import app

runner = CliRunner()

# Patch HiveRegistry at its source module since CLI imports it lazily
_REGISTRY_PATCH = "hive.shared.registry.HiveRegistry"


def test_help_shows_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "restart" in result.output
    assert "status" in result.output
    assert "logs" in result.output


def test_init_requires_name():
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0


class TestInit:
    @patch("hive.shared.supervisor.is_boot_config_installed", return_value=True)
    @patch("hive.shared.supervisor.reload_supervisord")
    @patch("hive.shared.supervisor.write_worker_block")
    @patch("subprocess.run")
    def test_scaffolds_worker_folder(
        self, mock_subproc, mock_write_block, mock_reload, mock_la, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        mock_registry = MagicMock()
        with patch(_REGISTRY_PATCH, return_value=mock_registry):
            result = runner.invoke(app, ["init", "test-worker"])

        assert result.exit_code == 0
        worker_dir = tmp_path / "test-worker"
        assert (worker_dir / "commands").is_dir()
        assert (worker_dir / "memory").is_dir()
        assert (worker_dir / "logs").is_dir()
        assert (worker_dir / "dashboard").is_dir()
        assert (worker_dir / "hive.toml").exists()
        assert (worker_dir / ".env").exists()
        assert (worker_dir / ".gitignore").exists()
        assert (worker_dir / "requirements.txt").exists()

    @patch("hive.shared.supervisor.is_boot_config_installed", return_value=True)
    @patch("hive.shared.supervisor.reload_supervisord")
    @patch("hive.shared.supervisor.write_worker_block")
    @patch("subprocess.run")
    def test_registers_worker(
        self, mock_subproc, mock_write_block, mock_reload, mock_la, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        mock_registry = MagicMock()
        with patch(_REGISTRY_PATCH, return_value=mock_registry):
            runner.invoke(app, ["init", "test-worker"])

        mock_registry.register.assert_called_once()
        mock_write_block.assert_called_once()
        mock_reload.assert_called_once()

    @patch("hive.shared.supervisor.is_boot_config_installed", return_value=True)
    @patch("hive.shared.supervisor.reload_supervisord")
    @patch("hive.shared.supervisor.write_worker_block")
    @patch("subprocess.run")
    def test_skips_existing_files(
        self, mock_subproc, mock_write_block, mock_reload, mock_la, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        worker_dir = tmp_path / "test-worker"
        worker_dir.mkdir()
        (worker_dir / "hive.toml").write_text("existing content")

        mock_registry = MagicMock()
        with patch(_REGISTRY_PATCH, return_value=mock_registry):
            runner.invoke(app, ["init", "test-worker"])

        assert (worker_dir / "hive.toml").read_text() == "existing content"

    @patch("hive.shared.supervisor.reload_supervisord")
    @patch("hive.shared.supervisor.write_worker_block")
    @patch("hive.shared.supervisor.write_comb_block")
    @patch("hive.shared.supervisor.ensure_supervisord_conf")
    @patch("hive.shared.supervisor.install_launchagent")
    @patch("hive.shared.supervisor.is_boot_config_installed", return_value=False)
    @patch("subprocess.run")
    def test_first_use_setup(
        self,
        mock_subproc,
        mock_la_check,
        mock_install_la,
        mock_ensure,
        mock_comb,
        mock_write_block,
        mock_reload,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        mock_registry = MagicMock()
        with patch(_REGISTRY_PATCH, return_value=mock_registry):
            runner.invoke(app, ["init", "test-worker"])

        mock_ensure.assert_called_once()
        mock_comb.assert_called_once()
        mock_install_la.assert_called_once()


class TestStart:
    def test_start_loads_config_and_starts(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        with (
            patch("hive.shared.supervisor.reload_supervisord"),
            patch("hive.shared.supervisor.write_worker_block"),
            patch(
                "hive.shared.supervisor.supervisorctl",
                return_value=MagicMock(stdout="worker-test: started"),
            ),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["start", str(tmp_path)])

        assert result.exit_code == 0
        assert "started" in result.output

    def test_start_fails_on_bad_config(self, tmp_path):
        result = runner.invoke(app, ["start", str(tmp_path)])
        assert result.exit_code == 1


class TestStop:
    def test_stop_calls_supervisorctl(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        with patch(
            "hive.shared.supervisor.supervisorctl",
            return_value=MagicMock(stdout="worker-test: stopped"),
        ):
            result = runner.invoke(app, ["stop", str(tmp_path)])

        assert result.exit_code == 0
        assert "stopped" in result.output


class TestRestart:
    def test_restart_calls_supervisorctl(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        with patch(
            "hive.shared.supervisor.supervisorctl",
            return_value=MagicMock(stdout="worker-test: restarted"),
        ):
            result = runner.invoke(app, ["restart", str(tmp_path)])

        assert result.exit_code == 0
        assert "restarted" in result.output


class TestRemove:
    def test_remove_unregisters_worker(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()
        with (
            patch("hive.shared.supervisor.supervisorctl"),
            patch("hive.shared.supervisor.remove_worker_block") as mock_remove_block,
            patch("hive.shared.supervisor.reload_supervisord"),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["remove", str(tmp_path)])

        assert result.exit_code == 0
        assert "unregistered" in result.output
        mock_remove_block.assert_called_once_with("test")
        mock_registry.unregister.assert_called_once_with("test")


class TestStatus:
    def test_status_shows_output(self):
        with patch(
            "hive.shared.supervisor.supervisorctl",
            return_value=MagicMock(stdout="worker-test   RUNNING   pid 123"),
        ):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "RUNNING" in result.output

    def test_status_no_workers(self):
        with patch(
            "hive.shared.supervisor.supervisorctl",
            return_value=MagicMock(stdout=""),
        ):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "No workers running" in result.output


class TestLogs:
    def test_logs_tails_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "out.log").write_text("line1\nline2\n")

        with patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["logs", str(tmp_path)])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "tail" in cmd
        assert str(log_dir / "out.log") in cmd

    def test_logs_missing_file(self, tmp_path):
        result = runner.invoke(app, ["logs", str(tmp_path)])
        assert result.exit_code == 1


class TestRun:
    def test_run_fails_on_bad_config(self, tmp_path):
        result = runner.invoke(app, ["run", str(tmp_path)])
        assert result.exit_code == 1


class TestUpgrade:
    def test_upgrade_command_exists(self):
        result = runner.invoke(app, ["upgrade", "--help"])
        assert result.exit_code == 0

    def test_upgrade_calls_all_migration_functions(self):
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        with (
            patch("hive.shared.supervisor.ensure_supervisord_conf") as mock_ensure,
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.install_launchagent") as mock_install,
            patch("hive.shared.supervisor.write_comb_block") as mock_comb,
            patch("hive.shared.supervisor.reload_supervisord") as mock_reload,
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        mock_ensure.assert_called_once()
        mock_install.assert_called_once()
        mock_comb.assert_called_once()
        mock_reload.assert_called_once()

    def test_upgrade_rewrites_worker_confs(self, tmp_path):
        from hive.shared.models import WorkerEntry

        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = [
            WorkerEntry(name="budget", path=str(tmp_path)),
        ]
        with (
            patch("hive.shared.supervisor.ensure_supervisord_conf"),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.install_launchagent"),
            patch("hive.shared.supervisor.reload_supervisord"),
            patch("hive.shared.supervisor.write_comb_block"),
            patch("hive.shared.supervisor.write_worker_block") as mock_write,
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        mock_write.assert_called_once_with("budget", tmp_path)

    def test_upgrade_daemon_mode_ok_skips_launchagent(self, tmp_path):
        daemon_plist = tmp_path / "com.hive.supervisord.plist"
        daemon_plist.write_text("RENDERED")
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        with (
            patch("hive.shared.supervisor.ensure_supervisord_conf"),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=True),
            patch("hive.shared.supervisor.LAUNCHDAEMON_PLIST", daemon_plist),
            patch("hive.shared.supervisor.render_launchdaemon_plist", return_value="RENDERED"),
            patch("hive.shared.supervisor.install_launchagent") as mock_install,
            patch("hive.shared.supervisor.write_comb_block"),
            patch("hive.shared.supervisor.reload_supervisord"),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "LaunchDaemon: OK" in result.output
        mock_install.assert_not_called()

    def test_upgrade_daemon_mode_reports_drift(self, tmp_path):
        daemon_plist = tmp_path / "com.hive.supervisord.plist"
        daemon_plist.write_text("STALE")
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        with (
            patch("hive.shared.supervisor.ensure_supervisord_conf"),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=True),
            patch("hive.shared.supervisor.LAUNCHDAEMON_PLIST", daemon_plist),
            patch("hive.shared.supervisor.render_launchdaemon_plist", return_value="RENDERED"),
            patch("hive.shared.supervisor.install_launchagent") as mock_install,
            patch("hive.shared.supervisor.write_comb_block"),
            patch("hive.shared.supervisor.reload_supervisord"),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "hive boot enable" in result.output
        mock_install.assert_not_called()


class TestVersion:
    def test_version_prints_installed_version(self):
        from hive import __version__

        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestUpdate:
    def test_update_fails_on_bad_config(self, tmp_path):
        result = runner.invoke(app, ["update", str(tmp_path)])
        assert result.exit_code == 1

    def test_update_up_to_date(self, tmp_path):
        from hive import __version__

        (tmp_path / "hive.toml").write_text(
            f'[worker]\nname = "test"\nhive_version = "{__version__}"\n'
        )
        with patch("hive.shared.changelog.find_changelog_text", return_value=None):
            result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_update_behind_lists_changelog_entries(self, tmp_path):
        (tmp_path / "hive.toml").write_text(
            '[worker]\nname = "test"\nhive_version = "0.0.1"\n'
        )
        changelog = (
            "## [Unreleased]\n\nnope\n\n"
            "## [0.2.0] - 2026-06-01\n\nFeature C.\n\n"
            "## [0.0.1] - 2026-01-01\n\nInitial.\n"
        )
        with (
            patch("hive.shared.changelog.find_changelog_text", return_value=changelog),
            patch("hive.__version__", "0.2.0"),
        ):
            result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 0
        assert "behind" in result.output
        assert "Feature C." in result.output
        assert "nope" not in result.output

    def test_update_pre_versioning_worker(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\n')
        with patch("hive.shared.changelog.find_changelog_text", return_value=None):
            result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 0
        assert "no recorded hive_version" in result.output

    def test_update_no_changelog_prints_link(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\nhive_version = "0.0.1"\n')
        with patch("hive.shared.changelog.find_changelog_text", return_value=None):
            result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 0
        assert "github.com" in result.output

    def test_update_worker_ahead_of_installed(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "test"\nhive_version = "9.9.9"\n')
        with (
            patch("hive.shared.changelog.find_changelog_text", return_value=None),
            patch("hive.__version__", "0.1.0b1"),
        ):
            result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 0
        assert "newer than the installed Hive" in result.output

    def test_update_unparseable_versions_warns_and_skips_drift(self, tmp_path):
        (tmp_path / "hive.toml").write_text(
            '[worker]\nname = "test"\nhive_version = "not-a-version"\n'
        )
        with (
            patch("hive.shared.changelog.find_changelog_text", return_value=None),
            patch("hive.__version__", "also-not-a-version"),
        ):
            result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 0
        assert "could not compare" in result.output
        assert "up to date" not in result.output
        assert "behind" not in result.output


class TestBoot:
    def test_boot_enable_non_tty_prints_instructions(self):
        with patch("hive.cli.app._stdin_is_tty", return_value=False):
            result = runner.invoke(app, ["boot", "enable"])
        assert result.exit_code == 1
        assert "sudo launchctl bootstrap system" in result.output

    def test_boot_enable_installs_daemon(self, tmp_path):
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        with (
            patch("hive.cli.app._stdin_is_tty", return_value=True),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.ensure_supervisord_conf") as mock_ensure,
            patch("hive.shared.supervisor.install_launchdaemon") as mock_install,
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["boot", "enable"])
        assert result.exit_code == 0
        mock_ensure.assert_called_once()
        mock_install.assert_called_once()

    def test_boot_enable_already_enabled_is_noop(self, tmp_path):
        daemon_plist = tmp_path / "com.hive.supervisord.plist"
        daemon_plist.write_text("RENDERED")
        with (
            patch("hive.cli.app._stdin_is_tty", return_value=True),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=True),
            patch("hive.shared.supervisor.LAUNCHDAEMON_PLIST", daemon_plist),
            patch("hive.shared.supervisor.render_launchdaemon_plist", return_value="RENDERED"),
            patch("hive.shared.supervisor.install_launchdaemon") as mock_install,
        ):
            result = runner.invoke(app, ["boot", "enable"])
        assert result.exit_code == 0
        assert "already" in result.output.lower()
        mock_install.assert_not_called()

    def test_boot_enable_warns_workers_without_auth_token(self, tmp_path):
        from hive.shared.models import WorkerEntry

        worker = tmp_path / "budget"
        worker.mkdir()
        (worker / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\n")
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = [
            WorkerEntry(name="budget", path=str(worker)),
        ]
        with (
            patch("hive.cli.app._stdin_is_tty", return_value=True),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.ensure_supervisord_conf"),
            patch("hive.shared.supervisor.install_launchdaemon"),
            patch("hive.shared.config.GLOBAL_ENV_PATH", tmp_path / "missing-global.env"),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["boot", "enable"])
        assert result.exit_code == 0
        assert "budget" in result.output
        assert "hive auth" in result.output

    def test_boot_enable_no_warning_with_global_token(self, tmp_path):
        from hive.shared.models import WorkerEntry

        worker = tmp_path / "budget"
        worker.mkdir()
        (worker / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\n")
        global_env = tmp_path / "global.env"
        global_env.write_text("CLAUDE_CODE_OAUTH_TOKEN=oat-123\n")
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = [
            WorkerEntry(name="budget", path=str(worker)),
        ]
        with (
            patch("hive.cli.app._stdin_is_tty", return_value=True),
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.ensure_supervisord_conf"),
            patch("hive.shared.supervisor.install_launchdaemon"),
            patch("hive.shared.config.GLOBAL_ENV_PATH", global_env),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["boot", "enable"])
        assert result.exit_code == 0
        assert "hive auth" not in result.output

    def test_boot_disable_non_tty_prints_instructions(self):
        with patch("hive.cli.app._stdin_is_tty", return_value=False):
            result = runner.invoke(app, ["boot", "disable"])
        assert result.exit_code == 1
        assert "sudo launchctl bootout" in result.output

    def test_boot_disable_restores_launchagent(self):
        with (
            patch("hive.cli.app._stdin_is_tty", return_value=True),
            patch("hive.shared.supervisor.uninstall_launchdaemon") as mock_uninstall,
            patch("hive.shared.supervisor.install_launchagent") as mock_agent,
            patch("hive.shared.supervisor.reload_supervisord") as mock_reload,
        ):
            result = runner.invoke(app, ["boot", "disable"])
        assert result.exit_code == 0
        mock_uninstall.assert_called_once()
        mock_agent.assert_called_once()
        mock_reload.assert_called_once()

    def test_boot_status_daemon(self):
        with patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=True):
            result = runner.invoke(app, ["boot", "status"])
        assert result.exit_code == 0
        assert "boot" in result.output.lower()

    def test_boot_status_agent(self):
        with (
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.is_launchagent_installed", return_value=True),
        ):
            result = runner.invoke(app, ["boot", "status"])
        assert result.exit_code == 0
        assert "login" in result.output.lower()

    def test_boot_status_neither(self):
        with (
            patch("hive.shared.supervisor.is_launchdaemon_installed", return_value=False),
            patch("hive.shared.supervisor.is_launchagent_installed", return_value=False),
        ):
            result = runner.invoke(app, ["boot", "status"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()


class TestAuth:
    def _patch_env_path(self, path):
        return patch("hive.shared.config.GLOBAL_ENV_PATH", path)

    def test_auth_writes_token(self, tmp_path):
        env_path = tmp_path / "config" / "hive" / ".env"
        with self._patch_env_path(env_path):
            result = runner.invoke(app, ["auth", "--token", "oat-123"])
        assert result.exit_code == 0
        assert env_path.read_text() == "CLAUDE_CODE_OAUTH_TOKEN=oat-123\n"
        assert (env_path.stat().st_mode & 0o777) == 0o600

    def test_auth_api_key_flag(self, tmp_path):
        env_path = tmp_path / ".env"
        with self._patch_env_path(env_path):
            result = runner.invoke(app, ["auth", "--api-key", "--token", "sk-456"])
        assert result.exit_code == 0
        assert env_path.read_text() == "ANTHROPIC_API_KEY=sk-456\n"

    def test_auth_replaces_existing_key_preserving_others(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("OTHER=keep\nCLAUDE_CODE_OAUTH_TOKEN=old\n")
        with self._patch_env_path(env_path):
            result = runner.invoke(app, ["auth", "--token", "new"])
        assert result.exit_code == 0
        assert env_path.read_text() == "OTHER=keep\nCLAUDE_CODE_OAUTH_TOKEN=new\n"

    def test_auth_prompts_when_no_token(self, tmp_path):
        env_path = tmp_path / ".env"
        with self._patch_env_path(env_path):
            result = runner.invoke(app, ["auth"], input="prompted-tok\n")
        assert result.exit_code == 0
        assert "CLAUDE_CODE_OAUTH_TOKEN=prompted-tok" in env_path.read_text()

    def test_auth_rejects_empty_token(self, tmp_path):
        env_path = tmp_path / ".env"
        with self._patch_env_path(env_path):
            result = runner.invoke(app, ["auth", "--token", "  "])
        assert result.exit_code == 1
        assert not env_path.exists()

    def test_auth_status_masks_value(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-abcdefghijklmnop\n")
        with self._patch_env_path(env_path):
            result = runner.invoke(app, ["auth", "--status"])
        assert result.exit_code == 0
        assert "sk-ant-oat01-abcdefghijklmnop" not in result.output
        assert "sk-ant-oat01…mnop" in result.output
        assert "ANTHROPIC_API_KEY: not set" in result.output

    def test_auth_status_when_file_missing(self, tmp_path):
        with self._patch_env_path(tmp_path / "missing.env"):
            result = runner.invoke(app, ["auth", "--status"])
        assert result.exit_code == 0
        assert "CLAUDE_CODE_OAUTH_TOKEN: not set" in result.output
