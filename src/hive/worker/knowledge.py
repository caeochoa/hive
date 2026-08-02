"""Shared, framework-agnostic helpers for Worker knowledge notes.

Owns all file I/O for memory/notes/, memory/index.md, and memory/log.md.
Deliberately stdlib-only — no claude_agent_sdk import — so runtime.py,
scheduler.py, and commands.py can call into this without violating Hive's
agent-framework-agnostic boundary (see agent.py's AgentRunner ABC).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_LOG_HEADER = (
    "<!-- Auto-maintained by Hive. Do not hand-edit — entries are appended "
    "deterministically and hand edits may be overwritten. -->\n"
)
_INDEX_HEADER = (
    "<!-- Auto-maintained by write_page. Do not hand-edit — entries are "
    "upserted by slug and hand edits may be overwritten. -->\n"
)
_SLUG_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def append_log(memory_dir: Path, entry_type: str, detail: str) -> None:
    """Append one entry to memory_dir/log.md, creating it with a header if needed."""
    log_path = memory_dir / "log.md"
    memory_dir.mkdir(parents=True, exist_ok=True)

    if not log_path.exists():
        log_path.write_text(_LOG_HEADER + "\n")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"## [{timestamp}] {entry_type} | {detail}\n")


def write_page(memory_dir: Path, slug: str, title: str, summary: str, content: str) -> None:
    """Write or overwrite a knowledge note, upsert its index.md line, and log it.

    Raises ValueError if slug is not kebab-case (lowercase letters, digits,
    hyphens only) — this also guards against path traversal, since slug is
    used to build a file path under memory_dir/notes/.
    """
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must be kebab-case "
            "(lowercase letters, digits, hyphens only)"
        )

    notes_dir = memory_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / f"{slug}.md").write_text(content)

    _upsert_index(memory_dir, slug, title, summary)
    append_log(memory_dir, "note", f"{slug} — {title}")


def _upsert_index(memory_dir: Path, slug: str, title: str, summary: str) -> None:
    """Replace the index.md line for slug in place, or append a new one."""
    index_path = memory_dir / "index.md"
    link_marker = f"](notes/{slug}.md)"
    date = datetime.now().strftime("%Y-%m-%d")
    new_line = f"- [{title}](notes/{slug}.md) — {summary} _(updated: {date})_\n"

    if index_path.exists():
        lines = index_path.read_text().splitlines(keepends=True)
    else:
        lines = [_INDEX_HEADER, "\n"]

    for i, existing in enumerate(lines):
        if link_marker in existing:
            lines[i] = new_line
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new_line)

    index_path.write_text("".join(lines))
