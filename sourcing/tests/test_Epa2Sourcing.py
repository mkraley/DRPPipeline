"""Tests for Epa2Sourcing."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.Epa2Sourcing import Epa2Sourcing
from sourcing.EpaSourcing import AGENCY
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

_ITEM_ID = "27cd1f0c43904460b27e9ab21449519b"
SAMPLE_ROW = {
    "url": f"https://edg-epa.hub.arcgis.com/datasets/{_ITEM_ID}",
    "title": "NPL Boundaries",
    "summary": "Superfund boundaries",
    "agency": AGENCY,
    "office": "U.S. EPA Office of Land",
    "record_id": _ITEM_ID,
    "item_type": "Feature Service",
}


class TestEpa2Sourcing(unittest.TestCase):
    """Tests for EDG Clip and Ship batch sourcing."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "epa2_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "epa2.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove the temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("sourcing.Epa2Sourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced Clip and Ship record."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        Epa2Sourcing(fetcher=fetcher).run(-1)

        fetcher.close.assert_called_once()
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "NPL Boundaries")
        self.assertEqual(projects[0]["agency"], AGENCY)
        self.assertEqual(projects[0]["office"], "U.S. EPA Office of Land")
        self.assertEqual(projects[0]["summary"], "Superfund boundaries")
        self.assertEqual(
            projects[0]["collection_notes"],
            "EDG Clip and Ship: Feature Service",
        )
        self.assertEqual(projects[0]["source_url"], SAMPLE_ROW["url"])

    @patch("sourcing.Epa2Sourcing.DuplicateChecker")
    def test_run_skips_item_already_stored_as_item_page(
        self,
        mock_checker_cls: MagicMock,
    ) -> None:
        """An item page already in Storage is not inserted again."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        existing = f"https://epa.maps.arcgis.com/home/item.html?id={_ITEM_ID}"
        self.storage.create_record(existing)
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        Epa2Sourcing(fetcher=fetcher).run(-1)

        self.assertEqual(self.storage.list_source_urls(), [existing])


if __name__ == "__main__":
    unittest.main()
