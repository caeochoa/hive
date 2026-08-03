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
_INDEX_ENTRY_SLUG_RE = re.compile(r"^- \[[^\]]*\]\(notes/([a-z0-9]+(?:-[a-z0-9]+)*)\.md\)")


def append_log(memory_dir: Path, entry_type: str, detail: str) -> None:
    """Append one entry to memory_dir/log.md, creating it with a header if needed."""
    log_path = memory_dir / "log.md"
    memory_dir.mkdir(parents=True, exist_ok=True)

    if not log_path.exists():
        log_path.write_text(_LOG_HEADER + "\n", encoding="utf-8")

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
    (notes_dir / f"{slug}.md").write_text(content, encoding="utf-8")

    _upsert_index(memory_dir, slug, title, summary)
    append_log(memory_dir, "note", f"{slug} — {title}")


def _sanitize_index_field(value: str, *, strip_brackets: bool = False) -> str:
    """Collapse embedded newlines (and CRs) to spaces so a value can never
    make an index.md entry span more than one physical line.

    If strip_brackets is set, ']' is also removed: that character sits right
    inside the markdown link's `[title]` text, and a stray ']' there would
    prematurely close the link and corrupt the rendered syntax. summary sits
    outside the `[]()` construct so a ']' there doesn't break parsing, but we
    still collapse its newlines for the same one-line-per-entry guarantee.
    """
    sanitized = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if strip_brackets:
        sanitized = sanitized.replace("]", "")
    return sanitized


def _upsert_index(memory_dir: Path, slug: str, title: str, summary: str) -> None:
    """Replace the index.md line for slug in place, or append a new one.

    Ownership of a line is decided structurally, not by substring search:
    _INDEX_ENTRY_SLUG_RE anchors at the start of the line and captures the
    slug out of the href immediately following the first ']'. Because
    title is guaranteed ']'-free (see _sanitize_index_field), that first
    ']' is always the link's own closing bracket — even if summary (free
    text, often LLM-generated) happens to contain literal markdown-link
    syntax like "](notes/other-slug.md)" later in the line.
    """
    index_path = memory_dir / "index.md"
    date = datetime.now().strftime("%Y-%m-%d")
    safe_title = _sanitize_index_field(title, strip_brackets=True)
    safe_summary = _sanitize_index_field(summary)
    new_line = f"- [{safe_title}](notes/{slug}.md) — {safe_summary} _(updated: {date})_\n"

    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = [_INDEX_HEADER, "\n"]

    for i, existing in enumerate(lines):
        match = _INDEX_ENTRY_SLUG_RE.match(existing)
        if match is not None and match.group(1) == slug:
            lines[i] = new_line
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new_line)

    index_path.write_text("".join(lines), encoding="utf-8")
