"""
Unit tests for Sourcing module.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

from sourcing import Sourcing


class TestSourcing(unittest.TestCase):
    """Test cases for Sourcing."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "sourcing"]

        Args.initialize()
        Logger.initialize(log_level="WARNING")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.sourcing = Sourcing()

    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()  # Reset singleton for next test
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    @patch.object(Sourcing, "get_candidate_urls", return_value=[])
    def test_run_returns_none(self, _mock_get: object) -> None:
        """Test run(-1) returns None after processing (no URLs)."""
        result = self.sourcing.run(-1)
        self.assertIsNone(result)

    @patch("sourcing.Sourcing.SpreadsheetCandidateFetcher")
    def test_get_candidate_urls_delegates_to_fetcher(self, mock_fetcher_cls: object) -> None:
        """Test get_candidate_urls(limit=...) delegates to SpreadsheetCandidateFetcher."""
        mock_fetcher = mock_fetcher_cls.return_value
        mock_fetcher.get_candidate_urls.return_value = ["https://example.com/1"]
        urls = self.sourcing.get_candidate_urls(limit=10)
        self.assertEqual(urls, ["https://example.com/1"])
        mock_fetcher_cls.assert_called_once()
        mock_fetcher.get_candidate_urls.assert_called_once_with(limit=10)

    def test_process_candidate_returns_string(self) -> None:
        """Test process_candidate() returns string status ("added", "duplicate", or "skipped")."""
        result = self.sourcing.process_candidate("https://example.com/data")
        self.assertIsInstance(result, str)
        self.assertIn(result, ["added", "duplicate", "skipped"])

    def test_is_duplicate_checks_storage(self) -> None:
        """Test is_duplicate() checks storage for existing URL."""
        # URL not in storage yet
        result = self.sourcing.is_duplicate("https://example.com/new")
        self.assertFalse(result)
        
        # Add URL to storage
        drpid = self.sourcing.create_storage_record_and_id("https://example.com/new")
        self.assertGreater(drpid, 0)
        
        # Now it should be a duplicate
        result = self.sourcing.is_duplicate("https://example.com/new")
        self.assertTrue(result)

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
