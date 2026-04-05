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
    @patch("hive.shared.supervisor.is_launchagent_installed", return_value=True)
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

    @patch("hive.shared.supervisor.is_launchagent_installed", return_value=True)
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

    @patch("hive.shared.supervisor.is_launchagent_installed", return_value=True)
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
    @patch("hive.shared.supervisor.is_launchagent_installed", return_value=False)
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


class TestStartComb:
    def test_start_with_comb_starts_comb_process(self, tmp_path):
        (tmp_path / "hive.toml").write_text(
            '[worker]\nname = "myworker"\n\n[comb]\ncells = [{type = "log", title = "Logs", source = "logs/out.log"}]\n'
        )
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        mock_supervisorctl = MagicMock(return_value=MagicMock(stdout="started"))

        with (
            patch("hive.shared.supervisor.reload_supervisord"),
            patch("hive.shared.supervisor.write_worker_block"),
            patch("hive.shared.supervisor.supervisorctl", mock_supervisorctl),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
            patch("hive.shared.supervisor.write_comb_app_block") as mock_write_comb,
            patch("hive.cli.app._find_free_port", return_value=8501),
        ):
            result = runner.invoke(app, ["start", str(tmp_path)])

        assert result.exit_code == 0
        mock_write_comb.assert_called_once()
        # Verify supervisorctl was called with comb-myworker start
        calls = [str(c) for c in mock_supervisorctl.call_args_list]
        assert any("comb-myworker" in c for c in calls)

    def test_start_without_comb_skips_comb_process(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "myworker"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()
        mock_registry.list_workers.return_value = []
        mock_supervisorctl = MagicMock(return_value=MagicMock(stdout="started"))

        with (
            patch("hive.shared.supervisor.reload_supervisord"),
            patch("hive.shared.supervisor.write_worker_block"),
            patch("hive.shared.supervisor.supervisorctl", mock_supervisorctl),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
            patch("hive.shared.supervisor.write_comb_app_block") as mock_write_comb,
        ):
            result = runner.invoke(app, ["start", str(tmp_path)])

        assert result.exit_code == 0
        mock_write_comb.assert_not_called()
        calls = [str(c) for c in mock_supervisorctl.call_args_list]
        assert not any("comb-myworker" in c for c in calls)


class TestStopComb:
    def test_stop_with_comb_stops_comb_process(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "myworker"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()
        mock_registry.get_comb_port.return_value = 8501
        mock_supervisorctl = MagicMock(return_value=MagicMock(stdout="stopped"))

        with (
            patch("hive.shared.supervisor.supervisorctl", mock_supervisorctl),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
            patch("hive.shared.supervisor.get_comb_app_conf_path"),
        ):
            result = runner.invoke(app, ["stop", str(tmp_path)])

        assert result.exit_code == 0
        calls = [str(c) for c in mock_supervisorctl.call_args_list]
        assert any("comb-myworker" in c for c in calls)

    def test_stop_without_comb_skips_comb_stop(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "myworker"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()
        mock_registry.get_comb_port.return_value = None
        mock_supervisorctl = MagicMock(return_value=MagicMock(stdout="stopped"))

        with (
            patch("hive.shared.supervisor.supervisorctl", mock_supervisorctl),
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["stop", str(tmp_path)])

        assert result.exit_code == 0
        calls = [str(c) for c in mock_supervisorctl.call_args_list]
        assert not any("comb-myworker" in c for c in calls)


class TestRemoveComb:
    def test_remove_calls_remove_comb_app_block(self, tmp_path):
        (tmp_path / "hive.toml").write_text('[worker]\nname = "myworker"\n')
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_ALLOWED_USER_ID=1\n"
        )
        mock_registry = MagicMock()

        with (
            patch("hive.shared.supervisor.supervisorctl"),
            patch("hive.shared.supervisor.remove_worker_block"),
            patch("hive.shared.supervisor.reload_supervisord"),
            patch("hive.shared.supervisor.remove_comb_app_block") as mock_remove_comb,
            patch(_REGISTRY_PATCH, return_value=mock_registry),
        ):
            result = runner.invoke(app, ["remove", str(tmp_path)])

        assert result.exit_code == 0
        mock_remove_comb.assert_called_once_with("myworker")
