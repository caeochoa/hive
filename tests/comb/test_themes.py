from hive.comb.themes import write_streamlit_theme


def test_write_terminal_dark_theme(tmp_path):
    write_streamlit_theme(tmp_path, "terminal-dark")
    config = (tmp_path / ".streamlit" / "config.toml").read_text()
    assert 'base = "dark"' in config
    assert "#0d1117" in config
    assert "#58a6ff" in config


def test_write_clean_light_theme(tmp_path):
    write_streamlit_theme(tmp_path, "clean-light")
    config = (tmp_path / ".streamlit" / "config.toml").read_text()
    assert 'base = "light"' in config
    assert "#f8fafc" in config
    assert "#3b82f6" in config


def test_write_bold_dark_theme(tmp_path):
    write_streamlit_theme(tmp_path, "bold-dark")
    config = (tmp_path / ".streamlit" / "config.toml").read_text()
    assert 'base = "dark"' in config
    assert "#1a1a2e" in config
    assert "#6366f1" in config


def test_unknown_theme_falls_back_to_dark(tmp_path):
    write_streamlit_theme(tmp_path, "nonexistent-theme")
    config = (tmp_path / ".streamlit" / "config.toml").read_text()
    assert 'base = "dark"' in config


def test_creates_streamlit_dir(tmp_path):
    write_streamlit_theme(tmp_path, "terminal-dark")
    assert (tmp_path / ".streamlit").is_dir()
    assert (tmp_path / ".streamlit" / "config.toml").is_file()


def test_idempotent(tmp_path):
    write_streamlit_theme(tmp_path, "terminal-dark")
    write_streamlit_theme(tmp_path, "clean-light")
    config = (tmp_path / ".streamlit" / "config.toml").read_text()
    assert 'base = "light"' in config
