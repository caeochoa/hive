from importlib.metadata import PackageNotFoundError, version

from hive.cli.app import app

try:
    __version__ = version("hive")
except PackageNotFoundError:
    __version__ = "0+unknown"


def main() -> None:
    app()
