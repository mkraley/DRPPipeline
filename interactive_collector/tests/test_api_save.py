"""Unit tests for interactive_collector.api_save."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.Args import Args
from utils.Logger import Logger


class TestSaveMetadataSheetClaim(unittest.TestCase):
    """Tests for Claimed sheet update after interactive save."""

    def setUp(self) -> None:
        """Initialize Args and an in-memory-style SQLite Storage."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "interactive_collector"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "ic_save_test.db"
        Args._config["db_path"] = str(self.db_path)

        from storage import Storage

        Storage.reset()
        Storage.initialize("StorageSQLLite", db_path=self.db_path)
        self.drpid_collected = Storage.create_record("https://example.com/collected")
        self.drpid_skip = Storage.create_record("https://example.com/skip")

    def tearDown(self) -> None:
        from storage import Storage

        Storage.reset()
        sys.argv = self._original_argv

    @patch("utils.sheet_claimed_update.claim_project_on_inventory_sheet")
    def test_save_metadata_claims_sheet_when_collected(self, mock_claim: object) -> None:
        """save_metadata calls claim_project_on_inventory_sheet for collected status."""
        from interactive_collector.api_save import save_metadata

        with tempfile.TemporaryDirectory() as folder:
            save_metadata(
                self.drpid_collected,
                folder,
                title="T",
                summary="S",
                keywords="k",
                agency="A",
                office="O",
                time_start="2020",
                time_end="2021",
                download_date="2024-01-01",
            )

        mock_claim.assert_called_once_with(self.drpid_collected)

    @patch("utils.sheet_claimed_update.claim_project_on_inventory_sheet")
    def test_save_metadata_skips_claim_for_skip_status(self, mock_claim: object) -> None:
        """save_metadata does not claim when status_override is a skip preset."""
        from interactive_collector.api_save import save_metadata

        save_metadata(
            self.drpid_skip,
            "",
            title="",
            summary="",
            keywords="",
            agency="",
            office="",
            time_start="",
            time_end="",
            download_date="",
            status_override="no_links",
        )

        mock_claim.assert_not_called()


if __name__ == "__main__":
    unittest.main()
