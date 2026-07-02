"""Tests for AdcGlobusSurvey."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.AdcGlobusSurvey import AdcGlobusSurvey
from collectors.GlobusPathInventory import GlobusInventorySummary


class TestAdcGlobusSurvey(unittest.TestCase):
    """Tests for Globus remote inventory survey."""

    def setUp(self) -> None:
        """Initialize Args and Logger for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "adc_globus_survey"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("collectors.AdcGlobusSurvey.Storage")
    @patch("collectors.AdcGlobusSurvey.build_transfer_service")
    def test_run_updates_status_notes_with_inventory(
        self,
        mock_build_service: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Survey writes inventory totals into status_notes without changing status."""
        mock_storage.get.return_value = {
            "status": "collected - external archive",
            "status_notes": (
                "External data URL: https://app.globus.org/file-manager?"
                "origin_id=src-ep&origin_path=%2Fnode29313%2F"
            ),
            "errors": "",
        }
        service = mock_build_service.return_value
        service.summarize_remote_path.return_value = GlobusInventorySummary(
            endpoint_id="src-ep",
            root_path="/node29313/",
            file_count=5,
            dir_count=1,
            total_bytes=40_000_000_000,
        )

        AdcGlobusSurvey().run(223)

        fields = mock_storage.update_record.call_args[0][1]
        self.assertIn("Globus remote inventory:", fields["status_notes"])
        self.assertIn("5 files", fields["status_notes"])
        self.assertNotIn("status", fields)

    @patch("collectors.AdcGlobusSurvey.Storage")
    def test_run_skips_when_already_surveyed(self, mock_storage: MagicMock) -> None:
        """Existing inventory line skips unless globus_survey_resurvey is true."""
        mock_storage.get.return_value = {
            "status": "collected - external archive",
            "status_notes": (
                "External data URL: https://app.globus.org/file-manager?x=1\n"
                "Globus remote inventory: 1 files in 0 dirs, 1.0 KB (surveyed 2026-01-01, path /a/)"
            ),
        }
        Args._config["globus_survey_resurvey"] = False
        AdcGlobusSurvey().run(223)
        mock_storage.update_record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
