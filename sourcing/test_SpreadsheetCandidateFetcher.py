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
    """Sample CSV matching Data_Inventories layout: URL, Claimed, Download Location."""
    return (
        "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
        ",,https://example.com/a,\r\n"
        ",alice,https://example.com/b,\r\n"
        ",,https://example.com/c,/path\r\n"
        ",,https://example.com/d,\r\n"
        ",,,\r\n"
    )


class TestSpreadsheetCandidateFetcher(unittest.TestCase):
    """Test cases for SpreadsheetCandidateFetcher."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
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
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/d"])
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
        """Test _row_passes_filter returns True when Claimed and Download Location empty."""
        row = {"Claimed (add your name)": "", "Download Location": ""}
        self.assertTrue(self.fetcher._row_passes_filter(row))

    def test_row_passes_filter_claimed_filled(self) -> None:
        """Test _row_passes_filter returns False when Claimed non-empty."""
        row = {"Claimed (add your name)": "alice", "Download Location": ""}
        self.assertFalse(self.fetcher._row_passes_filter(row))

    def test_row_passes_filter_download_location_filled(self) -> None:
        """Test _row_passes_filter returns False when Download Location non-empty."""
        row = {"Claimed (add your name)": "", "Download Location": "/path"}
        self.assertFalse(self.fetcher._row_passes_filter(row))

    def test_row_passes_filter_missing_columns_treated_empty(self) -> None:
        """Test _row_passes_filter treats missing columns as empty (for row dict access)."""
        # Note: In practice, columns are validated before calling this method.
        # This test verifies the method's behavior when keys are missing.
        self.assertTrue(self.fetcher._row_passes_filter({}))

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_respects_num_rows_limit(self, mock_fetch: object) -> None:
        """Test get_candidate_urls stops at num_rows limit."""
        # CSV has 4 valid URLs (a, d, and two more we'll add)
        csv_with_many = (
            "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
            ",,https://example.com/a,\r\n"
            ",alice,https://example.com/b,\r\n"
            ",,https://example.com/c,/path\r\n"
            ",,https://example.com/d,\r\n"
            ",,https://example.com/e,\r\n"
            ",,https://example.com/f,\r\n"
        )
        mock_fetch.return_value = csv_with_many
        
        # Set limit to 2
        Args._config["sourcing_num_rows"] = 2
        urls = self.fetcher.get_candidate_urls()
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/d"])
        
        # Reset
        Args._config["sourcing_num_rows"] = None

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_unlimited_when_num_rows_none(self, mock_fetch: object) -> None:
        """Test get_candidate_urls returns all URLs when num_rows is None."""
        csv_with_many = (
            "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
            ",,https://example.com/a,\r\n"
            ",,https://example.com/d,\r\n"
            ",,https://example.com/e,\r\n"
        )
        mock_fetch.return_value = csv_with_many
        
        Args._config["sourcing_num_rows"] = None
        urls = self.fetcher.get_candidate_urls()
        self.assertEqual(len(urls), 3)
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/d", "https://example.com/e"])

    @patch.object(SpreadsheetCandidateFetcher, "_fetch_sheet_csv")
    def test_get_candidate_urls_stops_early_when_limit_reached(self, mock_fetch: object) -> None:
        """Test that processing stops once limit is reached (doesn't process all rows)."""
        # Create CSV with many rows, but only first 2 pass filter
        csv_many_rows = (
            "Admin Notes,Claimed (add your name),URL,Download Location\r\n"
            ",,https://example.com/a,\r\n"
            ",,https://example.com/b,\r\n"
            ",alice,https://example.com/c,\r\n"  # Filtered out
            ",,https://example.com/d,/path\r\n"  # Filtered out
            ",,https://example.com/e,\r\n"  # Should not be processed
            ",,https://example.com/f,\r\n"  # Should not be processed
        )
        mock_fetch.return_value = csv_many_rows
        
        Args._config["sourcing_num_rows"] = 2
        urls = self.fetcher.get_candidate_urls()
        # Should stop after collecting 2 URLs, even though more valid URLs exist
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/b"])
        
        Args._config["sourcing_num_rows"] = None
