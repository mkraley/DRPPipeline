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

    @patch.object(Sourcing, "get_candidate_urls", return_value=([], 0))  # list of row dicts, skipped_count
    def test_run_returns_none(self, _mock_get: object) -> None:
        """Test run(-1) returns None after processing (no URLs)."""
        result = self.sourcing.run(-1)
        self.assertIsNone(result)

    @patch("sourcing.Sourcing.SpreadsheetCandidateFetcher")
    def test_get_candidate_urls_delegates_to_fetcher(self, mock_fetcher_cls: object) -> None:
        """Test get_candidate_urls(limit=...) delegates to SpreadsheetCandidateFetcher."""
        mock_fetcher = mock_fetcher_cls.return_value
        mock_fetcher.get_candidate_urls.return_value = (
            [{"url": "https://example.com/1", "office": "OHA", "agency": "CDC"}],
            0,
        )
        rows, skipped = self.sourcing.get_candidate_urls(limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://example.com/1")
        self.assertEqual(rows[0]["office"], "OHA")
        self.assertEqual(rows[0]["agency"], "CDC")
        self.assertEqual(skipped, 0)
        mock_fetcher_cls.assert_called_once()
        mock_fetcher.get_candidate_urls.assert_called_once_with(limit=10)


