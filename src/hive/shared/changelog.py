"""Keep a Changelog (https://keepachangelog.com) parsing for `hive update`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

_HEADER_RE = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\S+))?\s*$")

GITHUB_RAW_CHANGELOG_URL = "https://raw.githubusercontent.com/caeochoa/hive/main/CHANGELOG.md"
GITHUB_CHANGELOG_URL = "https://github.com/caeochoa/hive/blob/main/CHANGELOG.md"


@dataclass
class ChangelogEntry:
    version: str
    date: str | None
    body: str


def parse_changelog(text: str) -> list[ChangelogEntry]:
    """Split a Keep a Changelog file into entries by '## [x.y.z] - date' headers."""
    entries: list[ChangelogEntry] = []
    current: ChangelogEntry | None = None
    body_lines: list[str] = []

    def flush() -> None:
        if current is not None:
            entries.append(ChangelogEntry(current.version, current.date, "\n".join(body_lines).strip()))

    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            flush()
            current = ChangelogEntry(m.group("version"), m.group("date"), "")
            body_lines = []
        elif current is not None:
            body_lines.append(line)
    flush()
    return entries


def entries_between(
    entries: list[ChangelogEntry],
    from_version: str | None,
    to_version: str,
    include_unreleased: bool = False,
) -> list[ChangelogEntry]:
    """Entries with parseable versions in (from_version, to_version], newest first.

    from_version=None means "unknown baseline" — every parseable entry up to
    and including to_version is returned. Headers that aren't valid PEP 440
    versions (e.g. "Unreleased") are skipped unless include_unreleased and the
    header text is literally "Unreleased".

    Filters `entries` in place without re-sorting: the result preserves
    `entries`' original order, which is only newest-first if the input
    (e.g. from `parse_changelog`) already is, per Keep a Changelog convention.
    """
    try:
        to_v = Version(to_version)
    except InvalidVersion:
        return []

    from_v: Version | None = None
    if from_version is not None:
        try:
            from_v = Version(from_version)
        except InvalidVersion:
            from_v = None

    result = []
    for entry in entries:
        if entry.version.strip().lower() == "unreleased":
            if include_unreleased:
                result.append(entry)
            continue
        try:
            v = Version(entry.version)
        except InvalidVersion:
            continue
        if v > to_v:
            continue
        if from_v is not None and v <= from_v:
            continue
        result.append(entry)
    return result


def find_changelog_text() -> str | None:
    """Best-effort changelog lookup: local source checkout, then GitHub raw fetch."""
    local_path = Path(__file__).resolve().parents[3] / "CHANGELOG.md"
    if local_path.is_file():
        return local_path.read_text()

    try:
        import httpx

        resp = httpx.get(GITHUB_RAW_CHANGELOG_URL, timeout=3.0)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass

    return None
