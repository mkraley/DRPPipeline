"""Tests for NPS IRMA hierarchy SQLite tables."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from storage import Storage
from storage.NpsHierarchyStore import NpsHierarchyStore
from utils.Args import Args
from utils.Logger import Logger


class TestNpsHierarchyStore(unittest.TestCase):
    """Tests for nps_projects and nps_products persistence."""

    def setUp(self) -> None:
        """Create isolated Storage for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "nps_hierarchy"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "nps.db",
        )
        self.store = NpsHierarchyStore.from_storage()

    def tearDown(self) -> None:
        """Restore argv and remove temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_initialize_creates_nps_tables(self) -> None:
        """Storage initialization creates hierarchy tables."""
        cursor = self.storage.sqlite_connection().execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('nps_projects', 'nps_products') ORDER BY name"
        )
        names = [row[0] for row in cursor.fetchall()]
        self.assertEqual(names, ["nps_products", "nps_projects"])

    def test_upsert_and_replace_products(self) -> None:
        """Project upsert and product replace persist expected columns."""
        drpid = self.storage.create_record(
            "https://irma.nps.gov/DataStore/Reference/Profile/1001"
        )
        self.store.upsert_project(
            {
                "irma_project_id": 1001,
                "drpid": drpid,
                "irma_collection_id": 9688,
                "irma_program_id": 2310251,
                "collection_title": "IMD Programs",
                "program_title": "APHN",
                "project_title": "Keep Me",
                "breadcrumb": "Collection 9688 > Program 2310251 > Project 1001",
                "public_file_count": 3,
                "product_count": 1,
            }
        )
        self.store.replace_products(
            1001,
            [
                {
                    "irma_product_id": 2001,
                    "drpid": drpid,
                    "title": "Public Package",
                    "reference_type": "Data Package",
                    "source_url": "https://irma.nps.gov/DataStore/Reference/Profile/2001",
                    "visibility": "Public",
                    "file_access": "Public",
                    "public_file_count": 3,
                }
            ],
        )
        project = self.store.get_project(1001)
        self.assertIsNotNone(project)
        assert project is not None
        self.assertEqual(project["program_title"], "APHN")
        products = self.store.list_products(1001)
        self.assertEqual(products[0]["irma_product_id"], 2001)
        by_drpid = self.store.get_project_by_drpid(drpid)
        self.assertIsNotNone(by_drpid)
        assert by_drpid is not None
        self.assertEqual(by_drpid["irma_project_id"], 1001)
        self.assertEqual(len(self.store.list_products_for_drpid(drpid)), 1)

    def test_update_public_file_count_matches_collected_total(self) -> None:
        """Collected recursive file totals are written back to nps_projects."""
        drpid = self.storage.create_record(
            "https://irma.nps.gov/DataStore/Reference/Profile/1001"
        )
        self.store.upsert_project(
            {
                "irma_project_id": 1001,
                "drpid": drpid,
                "irma_collection_id": 9688,
                "irma_program_id": 2310251,
                "public_file_count": 3,
                "product_count": 1,
            }
        )
        self.store.update_public_file_count(drpid, 6)
        project = self.store.get_project_by_drpid(drpid)
        self.assertIsNotNone(project)
        assert project is not None
        self.assertEqual(project["public_file_count"], 6)

    def test_replace_products_drops_stale_rows(self) -> None:
        """Replacing products removes ids that are no longer listed."""
        drpid = self.storage.create_record(
            "https://irma.nps.gov/DataStore/Reference/Profile/1001"
        )
        self.store.upsert_project(
            {
                "irma_project_id": 1001,
                "drpid": drpid,
                "irma_collection_id": 9688,
                "irma_program_id": 2310251,
                "public_file_count": 1,
                "product_count": 1,
            }
        )
        self.store.replace_products(
            1001,
            [{"irma_product_id": 1, "drpid": drpid, "title": "Old"}],
        )
        self.store.replace_products(
            1001,
            [{"irma_product_id": 2, "drpid": drpid, "title": "New"}],
        )
        titles = [row["title"] for row in self.store.list_products(1001)]
        self.assertEqual(titles, ["New"])


if __name__ == "__main__":
    unittest.main()
