"""Tests for hive.worker.knowledge — write_page and log.md helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from hive.worker.knowledge import append_log, write_page


# ------------------------------------------------------------------ #
# append_log
# ------------------------------------------------------------------ #


def test_append_log_creates_file_with_header(tmp_path: Path) -> None:
    """First call creates log.md with a header comment plus one entry."""
    append_log(tmp_path, "command", "greet who=world")

    text = (tmp_path / "log.md").read_text()
    assert text.startswith("<!--")
    assert "command | greet who=world" in text


def test_append_log_appends_without_duplicating_header(tmp_path: Path) -> None:
    """Second call appends a new line; header appears exactly once."""
    append_log(tmp_path, "command", "first")
    append_log(tmp_path, "note", "second")

    text = (tmp_path / "log.md").read_text()
    assert text.count("<!--") == 1
    assert "command | first" in text
    assert "note | second" in text


def test_append_log_entry_format(tmp_path: Path) -> None:
    """Each entry matches '## [YYYY-MM-DD HH:MM] <type> | <detail>'."""
    import re

    append_log(tmp_path, "agent_prompt", "0 9 * * 1 — weekly summary")

    text = (tmp_path / "log.md").read_text()
    lines = [ln for ln in text.splitlines() if ln.startswith("## [")]
    assert len(lines) == 1
    assert re.fullmatch(
        r"## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] agent_prompt \| 0 9 \* \* 1 — weekly summary",
        lines[0],
    )


# ------------------------------------------------------------------ #
# write_page
# ------------------------------------------------------------------ #


def test_write_page_creates_note_file(tmp_path: Path) -> None:
    write_page(tmp_path, "thompson-thesis", "Thompson's Thesis", "Evolving view on X", "# Thompson\n\nBody text.")

    note = tmp_path / "notes" / "thompson-thesis.md"
    assert note.exists()
    assert note.read_text() == "# Thompson\n\nBody text."


def test_write_page_appends_index_entry(tmp_path: Path) -> None:
    write_page(tmp_path, "thompson-thesis", "Thompson's Thesis", "Evolving view on X", "body")

    index_text = (tmp_path / "index.md").read_text()
    assert "[Thompson's Thesis](notes/thompson-thesis.md)" in index_text
    assert "Evolving view on X" in index_text


def test_write_page_upserts_existing_index_line_in_place(tmp_path: Path) -> None:
    write_page(tmp_path, "a", "Title A", "Summary A", "body a")
    write_page(tmp_path, "b", "Title B", "Summary B", "body b")
    write_page(tmp_path, "a", "Title A", "Updated Summary A", "body a v2")

    lines = (tmp_path / "index.md").read_text().splitlines()
    a_lines = [ln for ln in lines if "](notes/a.md)" in ln]
    b_lines = [ln for ln in lines if "](notes/b.md)" in ln]
    assert len(a_lines) == 1
    assert "Updated Summary A" in a_lines[0]
    assert len(b_lines) == 1
    # 'a' line stays before 'b' line — updated in place, not moved to the end
    assert lines.index(a_lines[0]) < lines.index(b_lines[0])


def test_write_page_overwrites_note_content(tmp_path: Path) -> None:
    write_page(tmp_path, "a", "Title A", "Summary A", "old body")
    write_page(tmp_path, "a", "Title A", "Summary A", "new body")

    assert (tmp_path / "notes" / "a.md").read_text() == "new body"


def test_write_page_appends_note_log_entry(tmp_path: Path) -> None:
    write_page(tmp_path, "a", "Title A", "Summary A", "body")

    log_text = (tmp_path / "log.md").read_text()
    assert "note | a" in log_text
    assert "Title A" in log_text


def test_write_page_rejects_invalid_slug(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="slug"):
        write_page(tmp_path, "../escape", "Title", "Summary", "body")


def test_write_page_rejects_slug_with_slash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="slug"):
        write_page(tmp_path, "notes/nested", "Title", "Summary", "body")


def test_write_page_rejects_uppercase_slug(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="slug"):
        write_page(tmp_path, "Thompson", "Title", "Summary", "body")
