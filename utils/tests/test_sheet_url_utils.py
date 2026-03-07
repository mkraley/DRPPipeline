"""
Unit tests for sheet_url_utils.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.sheet_url_utils import get_gid_for_sheet_name, parse_spreadsheet_url

try:
    import google.oauth2.service_account  # noqa: F401
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


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


class TestGetGidForSheetName(unittest.TestCase):
    """Test cases for get_gid_for_sheet_name."""

    def test_returns_none_when_no_credentials_path(self) -> None:
        """When credentials_path is None, returns None (use first sheet)."""
        self.assertIsNone(get_gid_for_sheet_name("abc123", "CDC", None))

    def test_returns_none_when_empty_sheet_name(self) -> None:
        """When sheet_name is empty, returns None."""
        self.assertIsNone(get_gid_for_sheet_name("abc123", "", Path("creds.json")))

    @unittest.skipIf(not _GOOGLE_AVAILABLE, "google-auth not installed")
    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_returns_gid_when_sheet_name_matches(self, mock_creds: object, mock_build: object) -> None:
        """When API returns sheets, returns gid for the matching title."""
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"sheetId": 0, "title": "Sheet1"}},
                {"properties": {"sheetId": 101637367, "title": "CDC"}},
            ]
        }
        mock_build.return_value = mock_service
        gid = get_gid_for_sheet_name("spreadsheet_id", "CDC", Path("creds.json"))
        self.assertEqual(gid, "101637367")

    @unittest.skipIf(not _GOOGLE_AVAILABLE, "google-auth not installed")
    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_returns_none_when_sheet_name_not_found(self, mock_creds: object, mock_build: object) -> None:
        """When no sheet title matches, returns None."""
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]
        }
        mock_build.return_value = mock_service
        self.assertIsNone(get_gid_for_sheet_name("spreadsheet_id", "CDC", Path("creds.json")))
