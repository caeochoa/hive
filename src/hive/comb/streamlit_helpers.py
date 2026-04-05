"""Streamlit rendering helpers for Hive Comb dashboard cells."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from hive.comb.cells import (
    CellRenderError,
    render_chart_cell,
    render_file_cell,
    render_markdown_cell,
    render_metric_cell,
    render_status_cell,
    render_table_cell,
    resolve_latest_in_dir,
    tail_log_file,
)
from hive.shared.models import CombCell


def log_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a log cell by tailing the log file."""
    try:
        source = worker_dir / cell.source
        lines = tail_log_file(source, lines=200)
        st.code("\n".join(lines) if lines else "(no log entries yet)", language=None)
    except CellRenderError as e:
        st.error(str(e))


def file_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a file cell, auto-detecting markdown vs plain text."""
    try:
        source = worker_dir / cell.source
        resolved = resolve_latest_in_dir(source)
        if resolved != source:
            st.caption(resolved.name)
        if resolved.suffix == ".md":
            content = render_markdown_cell(resolved)
            st.markdown(content, unsafe_allow_html=True)
        else:
            content = render_file_cell(resolved)
            st.text(content)
    except CellRenderError as e:
        st.error(str(e))


def markdown_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a markdown cell."""
    try:
        source = worker_dir / cell.source
        resolved = resolve_latest_in_dir(source)
        if resolved != source:
            st.caption(resolved.name)
        content = render_markdown_cell(resolved)
        st.markdown(content, unsafe_allow_html=True)
    except CellRenderError as e:
        st.error(str(e))


def metric_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a metric cell as a Streamlit metric widget."""
    try:
        source = worker_dir / cell.source
        value = render_metric_cell(source, cell.key)
        st.metric(label=cell.title, value=value)
    except CellRenderError as e:
        st.error(str(e))


def status_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a status cell with a colour-coded emoji prefix."""
    try:
        source = worker_dir / cell.source
        result = render_status_cell(source, cell.key)
        _LEVEL_EMOJI = {
            "ok": "🟢",
            "warn": "🟡",
            "error": "🔴",
            "neutral": "⚪",
        }
        emoji = _LEVEL_EMOJI.get(result["level"], "⚪")
        st.metric(label=cell.title, value=f"{emoji} {result['value']}")
    except CellRenderError as e:
        st.error(str(e))


def table_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a table cell as an interactive Streamlit dataframe."""
    try:
        source = worker_dir / cell.source
        data = render_table_cell(source)
        if not data:
            st.info("No data")
            return
        import pandas as pd
        df = pd.DataFrame(data)
        st.dataframe(
            df,
            use_container_width=True,
            selection_mode="multi-row",
            on_select="rerun",
            key=f"table_{cell.title}",
        )
    except CellRenderError as e:
        st.error(str(e))


def chart_cell(cell: CombCell, worker_dir: Path) -> None:
    """Render a chart cell as a bar chart."""
    try:
        source = worker_dir / cell.source
        data = render_chart_cell(source, cell.key)
        import pandas as pd
        df = pd.DataFrame(data)
        df = df.set_index("label")
        st.bar_chart(df, use_container_width=True)
    except CellRenderError as e:
        st.error(str(e))


CELL_RENDERERS = {
    "log": log_cell,
    "file": file_cell,
    "markdown": markdown_cell,
    "metric": metric_cell,
    "status": status_cell,
    "table": table_cell,
    "chart": chart_cell,
}


def render_cell(cell: CombCell, worker_dir: Path) -> None:
    """Dispatch to the correct cell renderer based on cell.type."""
    fn = CELL_RENDERERS.get(cell.type)
    if fn is None:
        st.error(f"Unknown cell type: {cell.type!r}")
        return
    fn(cell, worker_dir)
