"""Tests for Comb cell rendering functions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive.comb.cells import CellRenderError, render_file_cell, render_metric_cell, tail_log_file


# --- render_file_cell ---


class TestRenderFileCell:
    def test_valid_file_returns_content(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("Hello, world!")
        assert render_file_cell(f) == "Hello, world!"

    def test_missing_file_raises_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.txt"
        with pytest.raises(CellRenderError, match="File not found"):
            render_file_cell(missing)


# --- render_metric_cell ---


class TestRenderMetricCell:
    def test_valid_json_with_key_returns_value(self, tmp_path: Path) -> None:
        f = tmp_path / "stats.json"
        f.write_text(json.dumps({"tasks_today": 42}))
        assert render_metric_cell(f, "tasks_today") == "42"

    def test_missing_file_raises_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.json"
        with pytest.raises(CellRenderError, match="File not found"):
            render_metric_cell(missing, "key")

    def test_invalid_json_raises_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json {{{")
        with pytest.raises(CellRenderError, match="Invalid JSON"):
            render_metric_cell(f, "key")

    def test_missing_key_raises_error(self, tmp_path: Path) -> None:
        f = tmp_path / "stats.json"
        f.write_text(json.dumps({"other_key": 1}))
        with pytest.raises(CellRenderError, match="not found"):
            render_metric_cell(f, "tasks_today")


# --- tail_log_file ---


class TestTailLogFile:
    def test_many_lines_returns_last_n(self, tmp_path: Path) -> None:
        f = tmp_path / "big.log"
        all_lines = [f"line {i}" for i in range(500)]
        f.write_text("\n".join(all_lines) + "\n")
        result = tail_log_file(f, lines=10)
        assert result == [f"line {i}" for i in range(490, 500)]

    def test_fewer_lines_returns_all(self, tmp_path: Path) -> None:
        f = tmp_path / "small.log"
        f.write_text("alpha\nbeta\ngamma\n")
        result = tail_log_file(f, lines=100)
        assert result == ["alpha", "beta", "gamma"]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.log"
        assert tail_log_file(missing) == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.log"
        f.write_text("")
        assert tail_log_file(f) == []
