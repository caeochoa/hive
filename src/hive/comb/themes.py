"""Streamlit theme config generation for Hive Comb dashboards."""

from __future__ import annotations

from pathlib import Path

_THEMES: dict[str, str] = {
    "terminal-dark": """\
[theme]
base = "dark"
primaryColor = "#58a6ff"
backgroundColor = "#0d1117"
secondaryBackgroundColor = "#161b22"
textColor = "#e6edf3"
""",
    "clean-light": """\
[theme]
base = "light"
primaryColor = "#3b82f6"
backgroundColor = "#f8fafc"
secondaryBackgroundColor = "#ffffff"
textColor = "#0f172a"
""",
    "bold-dark": """\
[theme]
base = "dark"
primaryColor = "#6366f1"
backgroundColor = "#1a1a2e"
secondaryBackgroundColor = "#16213e"
textColor = "#e2e8f0"
""",
}

_FALLBACK = """\
[theme]
base = "dark"
"""


def write_streamlit_theme(worker_dir: Path, theme_name: str) -> None:
    """Write .streamlit/config.toml in worker_dir for the given theme.

    Falls back to dark base if theme_name is unknown.
    """
    config_content = _THEMES.get(theme_name, _FALLBACK)
    streamlit_dir = worker_dir / ".streamlit"
    streamlit_dir.mkdir(parents=True, exist_ok=True)
    (streamlit_dir / "config.toml").write_text(config_content)
