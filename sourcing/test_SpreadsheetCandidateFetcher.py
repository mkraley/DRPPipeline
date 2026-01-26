"""
Unit tests for SpreadsheetCandidateFetcher.
"""

import sys
import unittest
from unittest.mock import patch

from utils.Args import Args
from utils.Logger import Logger

from sourcing.SpreadsheetCandidateFetcher import SpreadsheetCandidateFetcher


def _csv_candidates() -> str:
    """Sample CSV matching Data_Inventories layout: URL, Claimed, Download Location. Uses data.cdc.gov so _row_passes_filter passes."""
    return (
        "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
        ",,https://data.cdc.gov/a,\r\n"
        ",alice,https://data.cdc.gov/b,\r\n"
        ",,https://data.cdc.gov/c,/path\r\n"
        ",,https://data.cdc.gov/d,\r\n"
        ",,,\r\n"
    )


class TestSpreadsheetCandidateFetcher(unittest.TestCase):
    """Test cases for SpreadsheetCandidateFetcher."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.fetcher = SpreadsheetCandidateFetcher()

    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_returns_filtered_urls(self, mock_fetch: object) -> None:
        """Test get_candidate_urls fetches CSV, filters rows, returns URL list."""
        mock_fetch.return_value = _csv_candidates()
        urls = self.fetcher.get_candidate_urls()
        self.assertIsInstance(urls, list)
        self.assertEqual(urls, ["https://data.cdc.gov/a", "https://data.cdc.gov/d"])
        mock_fetch.assert_called_once()

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_missing_url_column_raises(self, mock_fetch: object) -> None:
        """Test get_candidate_urls raises ValueError when URL column missing."""
        mock_fetch.return_value = "ColA,ColB\r\n1,2\r\n"
        with self.assertRaises(ValueError) as cm:
            self.fetcher.get_candidate_urls()
        self.assertIn("missing required URL column", str(cm.exception))
        self.assertIn("URL", str(cm.exception))

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_missing_filter_column_raises(self, mock_fetch: object) -> None:
        """Test get_candidate_urls raises ValueError when filter column missing."""
        csv_no_dl = (
            "Admin Notes,Claimed (add your name),URL\r\n"
            ",,https://example.com/x\r\n"
            ",alice,https://example.com/y\r\n"
        )
        mock_fetch.return_value = csv_no_dl
        with self.assertRaises(ValueError) as cm:
            self.fetcher.get_candidate_urls()
        self.assertIn("missing required filter columns", str(cm.exception))
        self.assertIn("Download Location", str(cm.exception))

    def test_row_passes_filter_both_empty(self) -> None:
        """Test _row_passes_filter returns True when Claimed and Download Location empty and URL is data.cdc.gov."""
        row = {"Claimed (add your name)": "", "Download Location": "", "URL": "https://data.cdc.gov/x"}
        self.assertTrue(self.fetcher._row_passes_filter(row))

    def test_row_passes_filter_claimed_filled(self) -> None:
        """Test _row_passes_filter returns False when Claimed non-empty."""
        row = {"Claimed (add your name)": "alice", "Download Location": "", "URL": "https://data.cdc.gov/x"}
        self.assertFalse(self.fetcher._row_passes_filter(row))

    def test_row_passes_filter_download_location_filled(self) -> None:
        """Test _row_passes_filter returns False when Download Location non-empty."""
        row = {"Claimed (add your name)": "", "Download Location": "/path", "URL": "https://data.cdc.gov/x"}
        self.assertFalse(self.fetcher._row_passes_filter(row))

    def test_row_passes_filter_missing_url_treated_empty_fails(self) -> None:
        """Test _row_passes_filter returns False when URL is missing (empty); requires data.cdc.gov."""
        # Missing URL yields "".startswith("https://data.cdc.gov/") -> False.
        self.assertFalse(self.fetcher._row_passes_filter({}))

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_respects_limit(self, mock_fetch: object) -> None:
        """Test get_candidate_urls stops at limit (from caller)."""
        csv_with_many = (
            "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
            ",,https://data.cdc.gov/a,\r\n"
            ",alice,https://data.cdc.gov/b,\r\n"
            ",,https://data.cdc.gov/c,/path\r\n"
            ",,https://data.cdc.gov/d,\r\n"
            ",,https://data.cdc.gov/e,\r\n"
            ",,https://data.cdc.gov/f,\r\n"
        )
        mock_fetch.return_value = csv_with_many

        urls = self.fetcher.get_candidate_urls(limit=2)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls, ["https://data.cdc.gov/a", "https://data.cdc.gov/d"])

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_unlimited_when_limit_none(self, mock_fetch: object) -> None:
        """Test get_candidate_urls returns all URLs when limit is None."""
        csv_with_many = (
            "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
            ",,https://data.cdc.gov/a,\r\n"
            ",,https://data.cdc.gov/d,\r\n"
            ",,https://data.cdc.gov/e,\r\n"
        )
        mock_fetch.return_value = csv_with_many

        urls = self.fetcher.get_candidate_urls(limit=None)
        self.assertEqual(len(urls), 3)
        self.assertEqual(urls, ["https://data.cdc.gov/a", "https://data.cdc.gov/d", "https://data.cdc.gov/e"])

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_stops_early_when_limit_reached(self, mock_fetch: object) -> None:
        """Test that processing stops once limit is reached (doesn't process all rows)."""
        csv_many_rows = (
            "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
            ",,https://data.cdc.gov/a,\r\n"
            ",,https://data.cdc.gov/b,\r\n"
            ",alice,https://data.cdc.gov/c,\r\n"
            ",,https://data.cdc.gov/d,/path\r\n"
            ",,https://data.cdc.gov/e,\r\n"
            ",,https://data.cdc.gov/f,\r\n"
        )
        mock_fetch.return_value = csv_many_rows

        urls = self.fetcher.get_candidate_urls(limit=2)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls, ["https://data.cdc.gov/a", "https://data.cdc.gov/b"])
