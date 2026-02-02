"""
Unit tests for sheet_url_utils.
"""

import unittest

from utils.sheet_url_utils import parse_spreadsheet_url


class TestParseSpreadsheetUrl(unittest.TestCase):
    """Test cases for parse_spreadsheet_url."""

    def test_edit_url_with_gid_in_query(self) -> None:
        """Extract id and gid from edit URL with ?gid=."""
        url = (
            "https://docs.google.com/spreadsheets/d/1OYLn6NBWStOgPUTJfYpU0y0g4uY7roIPP4qC2YztgWY/"
            "edit?gid=101637367#gid=101637367"
        )
        sheet_id, gid = parse_spreadsheet_url(url)
        self.assertEqual(sheet_id, "1OYLn6NBWStOgPUTJfYpU0y0g4uY7roIPP4qC2YztgWY")
        self.assertEqual(gid, "101637367")

    def test_edit_url_gid_in_fragment_only(self) -> None:
        """Extract gid from fragment when missing in query."""
        url = "https://docs.google.com/spreadsheets/d/ABC123/edit#gid=42"
        sheet_id, gid = parse_spreadsheet_url(url)
        self.assertEqual(sheet_id, "ABC123")
        self.assertEqual(gid, "42")

    def test_export_url_no_gid(self) -> None:
        """No gid yields default '0' (first sheet)."""
        url = "https://docs.google.com/spreadsheets/d/XYZ789/export?format=csv"
        sheet_id, gid = parse_spreadsheet_url(url)
        self.assertEqual(sheet_id, "XYZ789")
        self.assertEqual(gid, "0")

    def test_invalid_url_raises(self) -> None:
        """URL without /d/ID/ pattern raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_spreadsheet_url("https://example.com/not-a-sheet")
        self.assertIn("Could not extract spreadsheet ID", str(cm.exception))
