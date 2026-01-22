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

from sourcing import Sourcing, SourceConfig


def _csv_candidates() -> str:
    """Sample CSV matching Data_Inventories layout: URL, Claimed, Download Location."""
    return (
        "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
        ",,https://example.com/a,\r\n"
        ",alice,https://example.com/b,\r\n"
        ",,https://example.com/c,/path\r\n"
        ",,https://example.com/d,\r\n"
        ",,,\r\n"
    )


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
        config = SourceConfig()
        result = self.sourcing.run([config])
        self.assertIsNone(result)

    @patch("sourcing.Sourcing.Sourcing._fetch_sheet_csv")
    def test_get_candidate_urls_returns_filtered_urls(self, mock_fetch: object) -> None:
        """Test get_candidate_urls() fetches CSV, filters rows, returns URL list."""
        mock_fetch.return_value = _csv_candidates()
        config = SourceConfig()
        urls = self.sourcing.get_candidate_urls(config)
        self.assertIsInstance(urls, list)
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/d"])
        mock_fetch.assert_called_once()

    @patch("sourcing.Sourcing.Sourcing._fetch_sheet_csv")
    def test_get_candidate_urls_missing_url_column_returns_empty(self, mock_fetch: object) -> None:
        """Test get_candidate_urls() returns [] and warns when URL column missing."""
        mock_fetch.return_value = "ColA,ColB\r\n1,2\r\n"
        config = SourceConfig()
        urls = self.sourcing.get_candidate_urls(config)
        self.assertEqual(urls, [])

    @patch("sourcing.Sourcing.Sourcing._fetch_sheet_csv")
    def test_get_candidate_urls_source_override(self, mock_fetch: object) -> None:
        """Test get_candidate_urls() uses source spreadsheet/tab when provided."""
        mock_fetch.return_value = _csv_candidates()
        url = "https://docs.google.com/spreadsheets/d/OVERRIDE_ID/edit?gid=999"
        config = SourceConfig(spreadsheet=url, tab="999")
        self.sourcing.get_candidate_urls(config)
        mock_fetch.assert_called_once_with("OVERRIDE_ID", "999")

    @patch("sourcing.Sourcing.Sourcing._fetch_sheet_csv")
    def test_get_candidate_urls_missing_filter_columns_excluded(self, mock_fetch: object) -> None:
        """Test get_candidate_urls() excludes missing filter columns and warns."""
        # CSV has URL and Claimed only; "Download Location" missing
        csv_no_dl = (
            "Admin Notes,Claimed (add your name),URL\r\n"
            ",,https://example.com/x\r\n"
            ",alice,https://example.com/y\r\n"
        )
        mock_fetch.return_value = csv_no_dl
        config = SourceConfig()
        urls = self.sourcing.get_candidate_urls(config)
        self.assertEqual(urls, ["https://example.com/x"])

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
