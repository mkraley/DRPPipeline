"""Unit tests for utils.sheet_claimed_update."""

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger
from utils.sheet_claimed_update import (
    claim_project_on_inventory_sheet,
    should_claim_after_collector_status,
    should_claim_inventory_sheet,
)


class TestShouldClaimInventorySheet(unittest.TestCase):
    """Tests for source-specific Claimed eligibility."""

    def setUp(self) -> None:
        """Initialize Args for source lookups."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()

    def tearDown(self) -> None:
        sys.argv = self._original_argv

    def test_bts_source_skips_claimed(self) -> None:
        """BTS catalog sourcing does not write inventory Claimed."""
        Args._config["source"] = "bts"
        self.assertFalse(should_claim_inventory_sheet())
        self.assertFalse(should_claim_inventory_sheet("bts"))

    def test_other_sources_claim(self) -> None:
        """Spreadsheet-sourced pipelines still write Claimed."""
        Args._config["source"] = "cdc"
        self.assertTrue(should_claim_inventory_sheet())


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

    @patch("publisher.inventory_sheet_updater.get_inventory_sheet_updater")
    def test_claim_calls_updater_when_configured(self, mock_factory: MagicMock) -> None:
        """Claim writes through the configured inventory sheet updater."""
        project = {
            "DRPID": 5,
            "source_url": "https://example.com/dataset",
            "status": "collected",
        }
        mock_updater = MagicMock()
        mock_updater.update_claimed.return_value = (True, None)
        mock_factory.return_value = mock_updater
        Args._config["google_sheet_id"] = "sheet1"
        Args._config["google_credentials"] = "creds.json"
        Args._config["google_username"] = "mkraley"

        ok, err = claim_project_on_inventory_sheet(5, project=project)

        self.assertTrue(ok)
        self.assertIsNone(err)
        mock_updater.update_claimed.assert_called_once_with(
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
