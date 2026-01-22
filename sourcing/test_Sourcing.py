"""
Unit tests for Sourcing module.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

from sourcing import Sourcing, SourceConfig


class TestSourcing(unittest.TestCase):
    """Test cases for Sourcing stubs."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]

        Args.initialize()
        Logger.initialize(log_level="WARNING")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.sourcing = Sourcing(self.storage)

    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.storage.close()
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_run_accepts_sources_and_returns_none(self) -> None:
        """Test run() accepts list of SourceConfig and returns None."""
        config = SourceConfig(spreadsheet="inventory.xlsx", tab="Sheet1")
        result = self.sourcing.run([config])
        self.assertIsNone(result)

    def test_get_candidate_urls_returns_list(self) -> None:
        """Test get_candidate_urls() returns a list of URLs."""
        config = SourceConfig(spreadsheet="inventory.xlsx", tab="Sheet1")
        urls = self.sourcing.get_candidate_urls(config)
        self.assertIsInstance(urls, list)
        self.assertEqual(urls, [])

    def test_process_candidate_returns_bool(self) -> None:
        """Test process_candidate() returns bool (stub returns False)."""
        result = self.sourcing.process_candidate("https://example.com/data")
        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_is_duplicate_returns_bool(self) -> None:
        """Test is_duplicate() returns bool (stub returns False)."""
        result = self.sourcing.is_duplicate("https://example.com/data")
        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_is_source_available_returns_bool(self) -> None:
        """Test is_source_available() returns bool (stub returns True)."""
        result = self.sourcing.is_source_available("https://example.com/data")
        self.assertIsInstance(result, bool)
        self.assertTrue(result)

    def test_create_storage_record_and_id_creates_record_and_returns_drpid(self) -> None:
        """Test create_storage_record_and_id() delegates to storage and returns DRPID."""
        url = "https://example.com/sourced"
        drpid = self.sourcing.create_storage_record_and_id(url)
        self.assertIsInstance(drpid, int)
        self.assertGreater(drpid, 0)

        record = self.storage.get(drpid)
        self.assertIsNotNone(record)
        self.assertEqual(record["source_url"], url)
