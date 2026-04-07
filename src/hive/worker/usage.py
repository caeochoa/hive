"""Subscription usage tracking for rate-limit-aware scheduled tasks."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_USAGE_PATH = Path.home() / ".config" / "hive" / "usage.json"

# Per-field staleness: the 5-hour window rolls over every 5h, so data older
# than 6h is genuinely expired. The 7-day window is much longer; 48h-old data
# is still highly representative.
_FIVE_HOUR_STALE = 6 * 3600
_SEVEN_DAY_STALE = 48 * 3600


class UsageStore:
    """Persists Claude subscription rate-limit snapshots to a shared JSON file.

    The file is namespaced by framework_key so multiple agent frameworks
    running on the same machine coexist without clobbering each other's data:

        {
            "claude_agent_sdk": {
                "recorded_at": 1234567890.0,
                "five_hour_pct": 75.3,
                "seven_day_pct": 42.1
            }
        }

    Writes are POSIX-atomic (write to .tmp then os.replace) so concurrent
    workers never produce torn reads.

    Missing or stale data always allows the task to run — we'd rather run than
    silently skip based on outdated info.
    """

    def __init__(
        self,
        path: Path = DEFAULT_USAGE_PATH,
        framework_key: str = "claude_agent_sdk",
    ) -> None:
        self._path = path
        self._framework_key = framework_key

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #

    def save(
        self,
        five_hour_pct: float | None,
        seven_day_pct: float | None,
    ) -> None:
        """Persist latest usage percentages under this framework's namespace."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Read-modify-write to preserve other frameworks' sections.
            full: dict = {}
            if self._path.exists():
                try:
                    full = json.loads(self._path.read_text())
                except (json.JSONDecodeError, OSError):
                    full = {}

            full[self._framework_key] = {
                "recorded_at": time.time(),
                "five_hour_pct": five_hour_pct,
                "seven_day_pct": seven_day_pct,
            }

            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(full, indent=2))
            os.replace(tmp, self._path)

            logger.debug(
                "[usage] saved five_hour=%s%% seven_day=%s%%",
                f"{five_hour_pct:.1f}" if five_hour_pct is not None else "n/a",
                f"{seven_day_pct:.1f}" if seven_day_pct is not None else "n/a",
            )
        except OSError:
            logger.warning("[usage] failed to write %s", self._path, exc_info=True)

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    def load(self) -> dict | None:
        """Return the raw stored section for this framework, or None if missing/corrupt."""
        if not self._path.exists():
            return None
        try:
            full = json.loads(self._path.read_text())
            return full.get(self._framework_key)
        except (json.JSONDecodeError, OSError, AttributeError):
            logger.warning("[usage] failed to read %s", self._path, exc_info=True)
            return None

    # ------------------------------------------------------------------ #
    # Check
    # ------------------------------------------------------------------ #

    def check_limits(
        self,
        five_hour_threshold: float | None,
        seven_day_threshold: float | None,
    ) -> tuple[bool, str | None]:
        """Return (ok, reason). ok=True means the task may run.

        Returns (True, None) when:
        - Neither threshold is set
        - Stored data is missing, corrupt, or stale for the relevant window
        """
        if five_hour_threshold is None and seven_day_threshold is None:
            return True, None

        data = self.load()
        if data is None:
            logger.debug("[usage] no stored data, allowing task to run")
            return True, None

        try:
            age = time.time() - float(data["recorded_at"])
        except (KeyError, TypeError, ValueError):
            logger.debug("[usage] malformed recorded_at, allowing task to run")
            return True, None

        if five_hour_threshold is not None:
            if age <= _FIVE_HOUR_STALE:
                pct = data.get("five_hour_pct")
                if pct is not None and pct >= five_hour_threshold:
                    return (
                        False,
                        f"5-hour usage {pct:.1f}% >= threshold {five_hour_threshold:.1f}%",
                    )
            else:
                logger.debug(
                    "[usage] five_hour_pct stale (%.1fh > 6h), skipping that check",
                    age / 3600,
                )

        if seven_day_threshold is not None:
            if age <= _SEVEN_DAY_STALE:
                pct = data.get("seven_day_pct")
                if pct is not None and pct >= seven_day_threshold:
                    return (
                        False,
                        f"7-day usage {pct:.1f}% >= threshold {seven_day_threshold:.1f}%",
                    )
            else:
                logger.debug(
                    "[usage] seven_day_pct stale (%.1fh > 48h), skipping that check",
                    age / 3600,
                )

        return True, None
