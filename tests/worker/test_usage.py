"""Tests for hive.worker.usage module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from hive.worker.usage import UsageStore, _FIVE_HOUR_STALE, _SEVEN_DAY_STALE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> UsageStore:
    return UsageStore(path=tmp_path / "usage.json")


@pytest.fixture
def store_b(tmp_path: Path) -> UsageStore:
    """Second framework store sharing the same file."""
    return UsageStore(path=tmp_path / "usage.json", framework_key="other_framework")


# ---------------------------------------------------------------------------
# save / load
# ---------------------------------------------------------------------------


class TestSave:
    def test_creates_file_with_namespace(self, store: UsageStore, tmp_path: Path) -> None:
        store.save(75.0, 42.0)
        data = json.loads((tmp_path / "usage.json").read_text())
        assert "claude_agent_sdk" in data
        assert data["claude_agent_sdk"]["five_hour_pct"] == 75.0
        assert data["claude_agent_sdk"]["seven_day_pct"] == 42.0
        assert "recorded_at" in data["claude_agent_sdk"]

    def test_preserves_other_framework_sections(
        self, store: UsageStore, store_b: UsageStore
    ) -> None:
        store.save(75.0, 42.0)
        store_b.save(10.0, 5.0)
        # Both sections coexist
        assert store.load() is not None
        assert store_b.load() is not None

    def test_overwrites_own_section(self, store: UsageStore) -> None:
        store.save(50.0, 20.0)
        store.save(80.0, 30.0)
        data = store.load()
        assert data["five_hour_pct"] == 80.0
        assert data["seven_day_pct"] == 30.0

    def test_handles_none_values(self, store: UsageStore) -> None:
        store.save(None, 42.0)
        data = store.load()
        assert data["five_hour_pct"] is None
        assert data["seven_day_pct"] == 42.0

    def test_atomic_write_cleans_up_tmp(self, store: UsageStore, tmp_path: Path) -> None:
        store.save(75.0, 42.0)
        assert not (tmp_path / "usage.tmp").exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = UsageStore(path=tmp_path / "deep" / "path" / "usage.json")
        nested.save(10.0, 5.0)
        assert nested.load() is not None


class TestLoad:
    def test_returns_none_when_file_missing(self, store: UsageStore) -> None:
        assert store.load() is None

    def test_returns_none_for_missing_key(
        self, store: UsageStore, store_b: UsageStore
    ) -> None:
        store_b.save(10.0, 5.0)
        # store's key ("claude_agent_sdk") doesn't exist yet
        assert store.load() is None

    def test_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        path = tmp_path / "usage.json"
        path.write_text("not json {{")
        s = UsageStore(path=path)
        assert s.load() is None

    def test_returns_data_when_valid(self, store: UsageStore) -> None:
        store.save(75.0, 42.0)
        data = store.load()
        assert data is not None
        assert data["five_hour_pct"] == 75.0


# ---------------------------------------------------------------------------
# check_limits — no thresholds
# ---------------------------------------------------------------------------


class TestCheckLimitsNoThresholds:
    def test_both_none_always_ok(self, store: UsageStore) -> None:
        ok, reason = store.check_limits(None, None)
        assert ok is True
        assert reason is None

    def test_no_data_always_ok(self, store: UsageStore) -> None:
        ok, reason = store.check_limits(80.0, 90.0)
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# check_limits — five_hour window
# ---------------------------------------------------------------------------


class TestCheckLimitsFiveHour:
    def test_blocks_when_above_threshold(self, store: UsageStore) -> None:
        store.save(85.0, 20.0)
        ok, reason = store.check_limits(five_hour_threshold=80.0, seven_day_threshold=None)
        assert ok is False
        assert "5-hour" in reason
        assert "85.0" in reason

    def test_allows_when_below_threshold(self, store: UsageStore) -> None:
        store.save(75.0, 20.0)
        ok, reason = store.check_limits(five_hour_threshold=80.0, seven_day_threshold=None)
        assert ok is True
        assert reason is None

    def test_allows_when_exactly_at_threshold(self, store: UsageStore) -> None:
        store.save(80.0, 20.0)
        ok, reason = store.check_limits(five_hour_threshold=80.0, seven_day_threshold=None)
        assert ok is False  # >= means at-threshold also blocks

    def test_stale_five_hour_data_allows(self, store: UsageStore) -> None:
        store.save(95.0, 20.0)
        with patch("hive.worker.usage.time") as mock_time:
            mock_time.time.return_value = time.time() + _FIVE_HOUR_STALE + 1
            ok, reason = store.check_limits(five_hour_threshold=80.0, seven_day_threshold=None)
        assert ok is True

    def test_fresh_five_hour_data_blocks(self, store: UsageStore) -> None:
        store.save(95.0, 20.0)
        ok, reason = store.check_limits(five_hour_threshold=80.0, seven_day_threshold=None)
        assert ok is False


# ---------------------------------------------------------------------------
# check_limits — seven_day window
# ---------------------------------------------------------------------------


class TestCheckLimitsSevenDay:
    def test_blocks_when_above_threshold(self, store: UsageStore) -> None:
        store.save(20.0, 92.0)
        ok, reason = store.check_limits(five_hour_threshold=None, seven_day_threshold=90.0)
        assert ok is False
        assert "7-day" in reason
        assert "92.0" in reason

    def test_allows_when_below_threshold(self, store: UsageStore) -> None:
        store.save(20.0, 80.0)
        ok, reason = store.check_limits(five_hour_threshold=None, seven_day_threshold=90.0)
        assert ok is True

    def test_stale_after_48h_allows(self, store: UsageStore) -> None:
        store.save(20.0, 95.0)
        with patch("hive.worker.usage.time") as mock_time:
            mock_time.time.return_value = time.time() + _SEVEN_DAY_STALE + 1
            ok, reason = store.check_limits(five_hour_threshold=None, seven_day_threshold=90.0)
        assert ok is True

    def test_fresh_within_48h_blocks(self, store: UsageStore) -> None:
        store.save(20.0, 95.0)
        ok, reason = store.check_limits(five_hour_threshold=None, seven_day_threshold=90.0)
        assert ok is False

    def test_five_hour_stale_but_seven_day_fresh_still_blocks(self, store: UsageStore) -> None:
        """If 5h data is stale but 7d data is fresh and over threshold, should still block."""
        store.save(95.0, 95.0)
        with patch("hive.worker.usage.time") as mock_time:
            # Past 5h staleness but within 48h staleness
            mock_time.time.return_value = time.time() + _FIVE_HOUR_STALE + 1
            ok, reason = store.check_limits(
                five_hour_threshold=80.0, seven_day_threshold=90.0
            )
        assert ok is False
        assert "7-day" in reason
