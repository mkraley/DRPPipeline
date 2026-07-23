"""Unit tests for utils.sheet_claimed_update."""

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger
from utils.sheet_claimed_update import (
    claim_project_on_inventory_sheet,
    should_claim_after_collector_status,
)


class TestShouldClaimAfterCollectorStatus(unittest.TestCase):
    """Tests for post-collector claim eligibility."""

    def test_collected_statuses(self) -> None:
        """Successful collected variants should claim."""
        self.assertTrue(should_claim_after_collector_status("collected"))
        self.assertTrue(should_claim_after_collector_status("collected - large file"))
        self.assertTrue(should_claim_after_collector_status("collected - external archive"))

    def test_error_and_other_statuses(self) -> None:
        """Error and pre-collect statuses should not claim."""
        self.assertFalse(should_claim_after_collector_status("sourced-error"))
        self.assertFalse(should_claim_after_collector_status("sourced"))
        self.assertFalse(should_claim_after_collector_status("no_links"))


class TestClaimProjectOnInventorySheet(unittest.TestCase):
    """Tests for claim_project_on_inventory_sheet."""

    def setUp(self) -> None:
        """Initialize Args for config lookups."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        sys.argv = self._original_argv

    @patch("publisher.GoogleSheetUpdater.GoogleSheetUpdater.update_claimed")
    def test_claim_calls_updater_when_configured(self, mock_update: MagicMock) -> None:
        """Claim writes through GoogleSheetUpdater when sheet is configured."""
        project = {
            "DRPID": 5,
            "source_url": "https://example.com/dataset",
            "status": "collected",
        }
        mock_update.return_value = (True, None)
        Args._config["google_sheet_id"] = "sheet1"
        Args._config["google_credentials"] = "creds.json"
        Args._config["google_username"] = "mkraley"

        ok, err = claim_project_on_inventory_sheet(5, project=project)

        self.assertTrue(ok)
        self.assertIsNone(err)
        mock_update.assert_called_once_with(
            "https://example.com/dataset",
            project=project,
        )

    def test_claim_skips_when_sheet_not_configured(self) -> None:
        """Missing google_sheet_id returns without raising."""
        Args._config["google_sheet_id"] = ""
        ok, err = claim_project_on_inventory_sheet(1)
        self.assertFalse(ok)
        self.assertIn("not configured", err or "")


if __name__ == "__main__":
    unittest.main()
