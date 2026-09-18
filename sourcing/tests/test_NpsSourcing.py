"""Tests for NpsSourcing orchestrator module."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.NpsSourcing import NpsSourcing
from storage import Storage
from storage.NpsHierarchyStore import NpsHierarchyStore
from utils.Args import Args
from utils.Logger import Logger

SAMPLE_ROW = {
    "url": "https://irma.nps.gov/DataStore/Reference/Profile/1001",
    "title": "Keep Me",
    "agency": "National Park Service",
    "office": "Inventory and Monitoring Division",
    "summary": "<p>Collection 9688: IMD Programs</p>",
    "keywords": "plants",
    "collection_notes": "Collection 9688: IMD Programs > Program 2310251: APHN > Project 1001: Keep Me",
    "record_id": "1001",
    "irma_project_id": 1001,
    "irma_program_id": 2310251,
    "irma_collection_id": 9688,
    "collection_title": "IMD Programs",
    "program_title": "APHN",
    "project_title": "Keep Me",
    "breadcrumb": "Collection 9688: IMD Programs > Program 2310251: APHN > Project 1001: Keep Me",
    "public_file_count": 3,
    "products": [
        {
            "irma_product_id": 2001,
            "title": "Public Package",
            "reference_type": "Data Package",
            "source_url": "https://irma.nps.gov/DataStore/Reference/Profile/2001",
            "visibility": "Public",
            "file_access": "Public",
            "public_file_count": 3,
        }
    ],
}


class TestNpsSourcing(unittest.TestCase):
    """Tests for NPS batch sourcing module."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "nps_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "nps.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("sourcing.NpsSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row_and_hierarchy(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced record plus nps_projects/nps_products rows."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_project_rows.return_value = [dict(SAMPLE_ROW)]

        NpsSourcing(fetcher=fetcher).run(-1)

        fetcher.close.assert_called_once()
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Keep Me")
        self.assertEqual(projects[0]["agency"], "National Park Service")
        self.assertIn("IMD Programs", projects[0]["collection_notes"])
        store = NpsHierarchyStore.from_storage()
        hierarchy = store.get_project(1001)
        self.assertIsNotNone(hierarchy)
        assert hierarchy is not None
        self.assertEqual(hierarchy["drpid"], projects[0]["DRPID"])
        self.assertEqual(hierarchy["irma_program_id"], 2310251)
        products = store.list_products(1001)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["title"], "Public Package")

    @patch("sourcing.NpsSourcing.DuplicateChecker")
    def test_run_skips_already_sourced_project_ids(self, mock_checker_cls: MagicMock) -> None:
        """Pending batch skips IRMA Project ids already present in Storage URLs."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        existing_url = SAMPLE_ROW["url"]
        self.storage.create_record(existing_url)
        fetcher = MagicMock()
        fetcher.list_project_rows.return_value = [
            dict(SAMPLE_ROW),
            {
                **SAMPLE_ROW,
                "url": "https://irma.nps.gov/DataStore/Reference/Profile/1003",
                "record_id": "1003",
                "irma_project_id": 1003,
                "title": "Second",
                "products": [],
            },
        ]

        NpsSourcing(fetcher=fetcher).run(-1)

        titles = {row["title"] for row in self.storage.list_eligible_projects("sourced", None)}
        self.assertEqual(titles, {"Second"})


if __name__ == "__main__":
    unittest.main()
