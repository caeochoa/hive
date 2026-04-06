"""Default Hive Comb dashboard — auto-generated from hive.toml cells.

Run via:
    streamlit run /path/to/default_app.py --server.port XXXX --server.headless true

Expects env var WORKER_DIR to point to the worker folder.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# Resolve worker directory from env
_worker_dir_env = os.environ.get("WORKER_DIR")
if not _worker_dir_env:
    st.error("WORKER_DIR environment variable is not set.")
    sys.exit(1)

WORKER_DIR = Path(_worker_dir_env).resolve()

# Load worker config (tolerates missing .env — no Telegram token needed for dashboard)
try:
    from hive.shared.config import load_worker_config_for_tui
    config = load_worker_config_for_tui(WORKER_DIR)
except Exception as e:
    st.error(f"Failed to load worker config: {e}")
    sys.exit(1)

from hive.comb.streamlit_helpers import render_cell  # noqa: E402

st.set_page_config(
    page_title=f"{config.name} — Hive Dashboard",
    layout="wide",
)

cells = config.comb_cells

if not cells:
    st.title(config.name)
    st.info("No dashboard cells configured in hive.toml.")
    st.stop()

# Sidebar navigation
st.sidebar.title(config.name)
selected = st.sidebar.radio(
    "View",
    options=[c.title for c in cells],
    label_visibility="collapsed",
)

# Find selected cell
cell = next(c for c in cells if c.title == selected)

# Render header + cell
st.header(cell.title)
render_cell(cell, WORKER_DIR)
