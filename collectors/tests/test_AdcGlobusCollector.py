"""Tests for AdcGlobusCollector."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.AdcGlobusCollector import AdcGlobusCollector, is_globus_external_archive


class TestAdcGlobusCollector(unittest.TestCase):
    """Tests for supplemental Globus ADC collection."""

    def setUp(self) -> None:
        """Initialize Args and Logger for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "adc_globus_collector"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_is_globus_external_archive_true(self) -> None:
        """Globus status_notes mark project as eligible."""
        project = {
            "status": "collected - external archive",
            "status_notes": (
                "External data URL: https://app.globus.org/file-manager?"
                "origin_id=abc&origin_path=%2Fnode%2F"
            ),
        }
        self.assertTrue(is_globus_external_archive(project))

    def test_is_globus_external_archive_false_for_portal(self) -> None:
        """Non-Globus external archive rows are not eligible."""
        project = {
            "status": "collected - external archive",
            "status_notes": "External data URL: https://www.lcacommons.gov/",
        }
        self.assertFalse(is_globus_external_archive(project))

    @patch("collectors.AdcGlobusCollector.Storage")
    @patch.object(AdcGlobusCollector, "_build_transfer_service")
    def test_run_submits_transfer_and_updates_status(
        self,
        mock_build_service: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Successful Globus transfer sets status collected."""
        folder = Path(__file__).parent / "_tmp_globus_collector"
        folder.mkdir(exist_ok=True)
        (folder / "data.txt").write_text("x", encoding="utf-8")

        mock_storage.get.side_effect = [
            {
                "status": "collected - external archive",
                "status_notes": (
                    "External data URL: https://app.globus.org/file-manager?"
                    "origin_id=src-ep&origin_path=%2Fnode29313%2F"
                ),
                "folder_path": str(folder),
                "errors": "",
            },
            {
                "status_notes": "External data URL: https://app.globus.org/...",
                "errors": "",
            },
            {"errors": ""},
        ]

        service = MagicMock()
        service.list_source_entries.return_value = [{"name": "file.csv"}]
        service.transfer_directory.return_value = "task-123"
        service.wait_for_task.return_value = "SUCCEEDED"
        mock_build_service.return_value = service

        try:
            AdcGlobusCollector().run(223)
            service.transfer_directory.assert_called_once()
            fields = mock_storage.update_record.call_args[0][1]
            self.assertEqual(fields["status"], "collected")
            self.assertIn("task-123", fields["status_notes"])
        finally:
            for path in folder.iterdir():
                path.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.AdcGlobusCollector.Storage")
    def test_run_skips_non_globus_project(self, mock_storage: MagicMock) -> None:
        """Non-Globus external archive rows are skipped without error."""
        mock_storage.get.return_value = {
            "status": "collected - external archive",
            "status_notes": "External data URL: https://example.com/",
            "folder_path": "C:\\Data\\DRP000001",
        }
        AdcGlobusCollector().run(1)
        mock_storage.update_record.assert_not_called()
