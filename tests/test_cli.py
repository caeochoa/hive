from typer.testing import CliRunner
from hive.cli.app import app

runner = CliRunner()


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
