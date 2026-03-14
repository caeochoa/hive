"""Cell rendering functions for the Comb dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path


class CellRenderError(Exception):
    """Raised when cell rendering fails."""


def render_file_cell(source: Path) -> str:
    """Read file content and return as string.

    Raises CellRenderError if file doesn't exist.
    """
    if not source.is_file():
        raise CellRenderError(f"File not found: {source}")
    return source.read_text()


def render_metric_cell(source: Path, key: str) -> str:
    """Load JSON from file, extract top-level key, return value as string.

    Raises CellRenderError if file missing, JSON invalid, or key not found.
    """
    if not source.is_file():
        raise CellRenderError(f"File not found: {source}")
    try:
        data = json.loads(source.read_text())
    except json.JSONDecodeError as exc:
        raise CellRenderError(f"Invalid JSON in {source}: {exc}") from exc
    if key not in data:
        raise CellRenderError(f"Key {key!r} not found in {source}")
    return str(data[key])


def tail_log_file(source: Path, lines: int = 100) -> list[str]:
    """Efficiently read last N lines from file by seeking from end.

    Returns [] if file doesn't exist. For small files, reads all lines
    and returns the last N.
    """
    if not source.is_file():
        return []

    file_size = source.stat().st_size
    if file_size == 0:
        return []

    # For small files (< 64KB), just read everything
    if file_size < 65536:
        all_lines = source.read_text().splitlines()
        return all_lines[-lines:]

    # For large files, seek from end to find enough lines
    with open(source, "rb") as f:
        # Start reading from the end in chunks
        chunk_size = 8192
        found_lines: list[bytes] = []
        remaining = file_size

        while remaining > 0 and len(found_lines) <= lines:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)

            # Split into lines and merge with previously found partial line
            chunk_lines = chunk.split(b"\n")
            if found_lines:
                # Merge last element of chunk with first element of found
                found_lines[0] = chunk_lines[-1] + found_lines[0]
                found_lines = chunk_lines[:-1] + found_lines
            else:
                found_lines = chunk_lines

        # Decode and return last N lines, filtering trailing empty
        decoded = [line.decode("utf-8", errors="replace") for line in found_lines]
        # Remove trailing empty string from final newline
        if decoded and decoded[-1] == "":
            decoded = decoded[:-1]
        return decoded[-lines:]
