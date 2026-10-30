"""Tests for inaccessible-download helpers and BudgetedDownload handling."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.BudgetedDownload import BudgetedDownload
from collectors.InaccessibleDownloads import (
    access_error_for_status,
    inaccessible_error_message,
    inaccessible_status_notes,
    partition_accessible,
)
from collectors.PlannedFile import PlannedFile
from utils.Logger import Logger
from utils.inventory_status import STATUS_COLLECTED, STATUS_COLLECTED_XLARGE


class TestInaccessibleDownloads(unittest.TestCase):
    """Access-error labels and all-vs-some error messages."""

    def test_access_error_for_denied_statuses(self) -> None:
        """401/403/404/410 are inaccessible; other codes are not."""
        self.assertEqual(access_error_for_status(404), "HTTP 404")
        self.assertEqual(access_error_for_status(403), "HTTP 403")
        self.assertIsNone(access_error_for_status(200))
        self.assertIsNone(access_error_for_status(500))

    def test_error_message_distinguishes_all_vs_some(self) -> None:
        """Status text says whether every file or only some are inaccessible."""
        files = [
            PlannedFile("a.zip", "https://ex/a", access_error="HTTP 404"),
            PlannedFile("b.zip", "https://ex/b", access_error="HTTP 403"),
        ]
        all_msg = inaccessible_error_message(files, 2) or ""
        some_msg = inaccessible_error_message(files[:1], 3) or ""
        self.assertIn("All 2", all_msg)
        self.assertIn("none were successfully accessed", all_msg)
        self.assertIn("1 of 3", some_msg)
        self.assertIn("2 were successfully accessed", some_msg)

    def test_partition_and_notes(self) -> None:
        """Inaccessible files are split out and described per file."""
        files = [
            PlannedFile("ok.zip", "https://ex/ok", size_bytes=10),
            PlannedFile("gone.zip", "https://ex/gone", access_error="HTTP 404"),
        ]
        accessible, inaccessible = partition_accessible(files)
        self.assertEqual(len(accessible), 1)
        self.assertEqual(len(inaccessible), 1)
        notes = inaccessible_status_notes(inaccessible)
        self.assertTrue(any("HTTP 404" in note and "gone.zip" in note for note in notes))


class TestBudgetedDownloadInaccessible(unittest.TestCase):
    """Inaccessible probes must not force xlarge unknown-size deferral."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize logging once."""
        Logger.initialize(log_level="WARNING")

    @patch("collectors.BudgetedDownload.record_error")
    def test_all_inaccessible_are_errors_not_deferred(
        self, mock_record_error: MagicMock
    ) -> None:
        """All inaccessible files record an error and are not deferred as xlarge."""
        folder = Path(tempfile.mkdtemp())
        files = [
            PlannedFile("a.zip", "https://ex/a", access_error="HTTP 404"),
            PlannedFile("b.zip", "https://ex/b", access_error="HTTP 403"),
        ]
        calls: list[str] = []

        def download_one(item: PlannedFile, dest: Path) -> bool:
            calls.append(item.relative_path)
            dest.write_bytes(b"x")
            return True

        outcome = BudgetedDownload().download_until_budget(1, folder, files, download_one)
        self.assertEqual(calls, [])
        self.assertFalse(outcome.deferred)
        self.assertTrue(any("All 2" in note for note in outcome.notes))
        mock_record_error.assert_called_once()
        self.assertIn("All 2", mock_record_error.call_args[0][1])
        status = BudgetedDownload().commit_inventory(1, folder, files)
        self.assertEqual(status, STATUS_COLLECTED)

    @patch("collectors.BudgetedDownload.record_error")
    def test_some_inaccessible_still_download_others(
        self, mock_record_error: MagicMock
    ) -> None:
        """Accessible files download; inaccessible ones are noted as partial errors."""
        folder = Path(tempfile.mkdtemp())
        files = [
            PlannedFile("ok.bin", "https://ex/ok", size_bytes=4),
            PlannedFile("gone.bin", "https://ex/gone", access_error="HTTP 404"),
        ]

        def download_one(item: PlannedFile, dest: Path) -> bool:
            dest.write_bytes(b"data")
            return True

        outcome = BudgetedDownload().download_until_budget(1, folder, files, download_one)
        self.assertTrue((folder / "ok.bin").is_file())
        self.assertFalse((folder / "gone.bin").exists())
        self.assertFalse(outcome.deferred)
        self.assertTrue(any("1 of 2" in note for note in outcome.notes))
        mock_record_error.assert_called_once()
        status = BudgetedDownload().commit_inventory(1, folder, files)
        self.assertNotEqual(status, STATUS_COLLECTED_XLARGE)


if __name__ == "__main__":
    unittest.main()
