"""Tests for Comb build step in comb start/restart commands."""

from pathlib import Path
from unittest import mock

import pytest
import typer

from hive.cli.app import _build_frontend


def test_build_frontend_with_node_modules():
    """Test _build_frontend when node_modules already exists."""
    with mock.patch("subprocess.run") as mock_run:
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        frontend_dir = Path("/fake/frontend")
        with mock.patch("pathlib.Path.is_dir", return_value=True):
            _build_frontend(frontend_dir)

        # Should only call npm run build (not npm install)
        assert mock_run.call_count == 1
        call_args = mock_run.call_args
        assert call_args[0][0] == ["npm", "run", "build"]
        assert call_args[1]["cwd"] == str(frontend_dir)


def test_build_frontend_installs_dependencies():
    """Test _build_frontend installs npm dependencies when node_modules is missing."""
    with mock.patch("subprocess.run") as mock_run:
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        frontend_dir = Path("/fake/frontend")

        # Simulate node_modules not existing on first call, then exists on subsequent calls
        is_dir_calls = [False, True]
        with mock.patch("pathlib.Path.is_dir", side_effect=lambda: is_dir_calls.pop(0)):
            _build_frontend(frontend_dir)

        # Should call npm install and npm run build
        assert mock_run.call_count == 2

        # First call: npm install
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0] == ["npm", "install"]
        assert first_call[1]["cwd"] == str(frontend_dir)

        # Second call: npm run build
        second_call = mock_run.call_args_list[1]
        assert second_call[0][0] == ["npm", "run", "build"]
        assert second_call[1]["cwd"] == str(frontend_dir)


def test_build_frontend_install_failure():
    """Test _build_frontend raises typer.Exit when npm install fails."""
    with mock.patch("subprocess.run") as mock_run:
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stderr = "npm install error"
        mock_run.return_value = mock_result

        frontend_dir = Path("/fake/frontend")
        with mock.patch("pathlib.Path.is_dir", return_value=False):
            with pytest.raises(typer.Exit) as exc_info:
                _build_frontend(frontend_dir)

            assert exc_info.value.exit_code == 1


def test_build_frontend_build_failure():
    """Test _build_frontend raises typer.Exit when npm run build fails."""
    with mock.patch("subprocess.run") as mock_run:
        install_result = mock.Mock()
        install_result.returncode = 0

        build_result = mock.Mock()
        build_result.returncode = 1
        build_result.stderr = "build error"

        mock_run.side_effect = [install_result, build_result]

        frontend_dir = Path("/fake/frontend")
        is_dir_calls = [False, True]
        with mock.patch("pathlib.Path.is_dir", side_effect=lambda: is_dir_calls.pop(0)):
            with pytest.raises(typer.Exit) as exc_info:
                _build_frontend(frontend_dir)

            assert exc_info.value.exit_code == 1


def test_build_frontend_capture_output():
    """Test _build_frontend passes capture_output and text flags to subprocess.run."""
    with mock.patch("subprocess.run") as mock_run:
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        frontend_dir = Path("/fake/frontend")
        with mock.patch("pathlib.Path.is_dir", return_value=True):
            _build_frontend(frontend_dir)

        # Check that capture_output and text flags are set
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True
