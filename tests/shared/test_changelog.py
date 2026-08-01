from hive.shared.changelog import entries_between, parse_changelog

SAMPLE = """\
# Changelog

## [Unreleased]

### Added
- Something not yet released.

## [0.3.0] - 2026-06-01

### Added
- Feature C.

## [0.2.0] - 2026-05-01

### Changed
- **Breaking:** renamed field X to Y.

## [0.1.0] - 2026-04-01

Initial release.
"""


def test_parse_changelog_splits_entries():
    entries = parse_changelog(SAMPLE)
    versions = [e.version for e in entries]
    assert versions == ["Unreleased", "0.3.0", "0.2.0", "0.1.0"]


def test_parse_changelog_captures_date_and_body():
    entries = parse_changelog(SAMPLE)
    entry = next(e for e in entries if e.version == "0.3.0")
    assert entry.date == "2026-06-01"
    assert "Feature C." in entry.body


def test_parse_changelog_undated_entry():
    entries = parse_changelog(SAMPLE)
    entry = next(e for e in entries if e.version == "Unreleased")
    assert entry.date is None


def test_entries_between_in_range():
    entries = parse_changelog(SAMPLE)
    result = entries_between(entries, "0.1.0", "0.3.0")
    versions = [e.version for e in result]
    assert versions == ["0.3.0", "0.2.0"]


def test_entries_between_from_none_includes_all_history():
    entries = parse_changelog(SAMPLE)
    result = entries_between(entries, None, "0.2.0")
    versions = [e.version for e in result]
    assert versions == ["0.2.0", "0.1.0"]


def test_entries_between_equal_versions_is_empty():
    entries = parse_changelog(SAMPLE)
    result = entries_between(entries, "0.2.0", "0.2.0")
    assert result == []


def test_entries_between_excludes_unreleased_by_default():
    entries = parse_changelog(SAMPLE)
    result = entries_between(entries, "0.1.0", "0.3.0")
    assert all(e.version != "Unreleased" for e in result)


def test_entries_between_includes_unreleased_when_requested():
    entries = parse_changelog(SAMPLE)
    result = entries_between(entries, "0.1.0", "0.3.0", include_unreleased=True)
    assert any(e.version == "Unreleased" for e in result)


def test_entries_between_skips_unparseable_headers():
    text = "## [notaversion]\nbody\n\n## [0.2.0] - 2026-05-01\nbody\n"
    entries = parse_changelog(text)
    result = entries_between(entries, None, "0.2.0")
    versions = [e.version for e in result]
    assert versions == ["0.2.0"]
