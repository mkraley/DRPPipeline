"""Tests for hourly upload and publish counts read from the pipeline log."""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from dashboard.hourly_throughput import HourlyThroughput


def _line(ts: str, level: str, drpid: str, message: str) -> str:
    """Format one pipeline log line."""
    return f"{ts} - {level} - [P1] [T1] [{drpid}] {message}\n"


class TestHourlyThroughput(unittest.TestCase):
    """Count finished upload and publish projects into wall-clock hours."""

    def setUp(self) -> None:
        """Create a temporary log file."""
        self._tmpdir = TemporaryDirectory()
        self.log_path = Path(self._tmpdir.name) / "drp_pipeline.log"

    def tearDown(self) -> None:
        """Remove the temporary log file."""
        self._tmpdir.cleanup()

    def test_counts_success_and_failure_by_hour(self) -> None:
        """Each finished project lands in its hour as a success or a failure."""
        self.log_path.write_text(
            "".join(
                [
                    _line(
                        "2026-11-05 15:01:00",
                        "INFO",
                        "1",
                        "Orchestrator starting project module='upload' DRPID=1",
                    ),
                    _line(
                        "2026-11-05 15:10:00",
                        "INFO",
                        "1",
                        "Orchestrator finished project module='upload' DRPID=1",
                    ),
                    _line(
                        "2026-11-05 15:11:00",
                        "INFO",
                        "2",
                        "Orchestrator starting project module='upload' DRPID=2",
                    ),
                    _line("2026-11-05 15:12:00", "ERROR", "2", "Upload failed: timeout"),
                    _line(
                        "2026-11-05 15:20:00",
                        "INFO",
                        "2",
                        "Orchestrator finished project module='upload' DRPID=2",
                    ),
                    _line(
                        "2026-11-05 14:05:00",
                        "INFO",
                        "3",
                        "Orchestrator starting project module='publish' DRPID=3",
                    ),
                    _line(
                        "2026-11-05 14:40:00",
                        "INFO",
                        "3",
                        "Orchestrator finished project module='publish' DRPID=3",
                    ),
                    _line(
                        "2026-11-04 10:01:00",
                        "INFO",
                        "4",
                        "Orchestrator starting project module='publish' DRPID=4",
                    ),
                    _line("2026-11-04 10:02:00", "ERROR", "4", "Publish failed: missing"),
                    _line(
                        "2026-11-04 10:03:00",
                        "INFO",
                        "4",
                        "Orchestrator finished project module='publish' DRPID=4",
                    ),
                ]
            ),
            encoding="utf-8",
        )
        payload = HourlyThroughput(self.log_path).series(
            now=datetime(2026, 11, 5, 15, 40),
            hours=48,
        )
        hours = payload["hours"]
        series = payload["series"]
        self.assertEqual(len(hours), 48)
        self.assertEqual(series["upload_ok"][hours.index("11-05 15")], 1)
        self.assertEqual(series["upload_fail"][hours.index("11-05 15")], 1)
        self.assertEqual(series["publish_ok"][hours.index("11-05 14")], 1)
        self.assertEqual(series["publish_fail"][hours.index("11-04 10")], 1)
        self.assertEqual(sum(series["upload_ok"]), 1)
        self.assertEqual(sum(series["publish_fail"]), 1)

    def test_second_read_appends_only_new_lines(self) -> None:
        """A later finish is counted without reprocessing the earlier project."""
        self.log_path.write_text(
            _line(
                "2026-11-05 15:01:00",
                "INFO",
                "1",
                "Orchestrator starting project module='upload' DRPID=1",
            )
            + _line(
                "2026-11-05 15:02:00",
                "INFO",
                "1",
                "Orchestrator finished project module='upload' DRPID=1",
            ),
            encoding="utf-8",
        )
        reader = HourlyThroughput(self.log_path)
        now = datetime(2026, 11, 5, 15, 40)
        first = reader.series(now=now)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                _line(
                    "2026-11-05 15:20:00",
                    "INFO",
                    "8",
                    "Orchestrator starting project module='publish' DRPID=8",
                )
            )
            handle.write(
                _line(
                    "2026-11-05 15:21:00",
                    "INFO",
                    "8",
                    "Orchestrator finished project module='publish' DRPID=8",
                )
            )
        second = reader.series(now=now)
        hour = second["hours"].index("11-05 15")
        self.assertEqual(first["series"]["upload_ok"][hour], 1)
        self.assertEqual(second["series"]["upload_ok"][hour], 1)
        self.assertEqual(second["series"]["publish_ok"][hour], 1)

    def test_missing_log_returns_empty_hours(self) -> None:
        """A missing log still returns 48 zero hours."""
        payload = HourlyThroughput(self.log_path).series(
            now=datetime(2026, 11, 5, 15, 40)
        )
        self.assertEqual(len(payload["hours"]), 48)
        self.assertEqual(sum(payload["series"]["upload_ok"]), 0)
