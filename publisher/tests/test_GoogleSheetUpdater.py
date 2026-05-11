"""
Unit tests for GoogleSheetUpdater (publisher module).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from publisher.GoogleSheetUpdater import (
    DOWNLOAD_LOCATION_TEMPLATE,
    GoogleSheetUpdater,
)

# Skip tests that mock Google API when the API is not installed
import publisher.GoogleSheetUpdater as _gsu_module
_GOOGLE_AVAILABLE = getattr(_gsu_module, "_GOOGLE_SHEETS_AVAILABLE", False)
skip_if_no_google = unittest.skipIf(not _GOOGLE_AVAILABLE, "Google Sheets API not installed")


class TestGoogleSheetUpdater(unittest.TestCase):
    """Test cases for GoogleSheetUpdater."""

    def setUp(self) -> None:
        """Initialize Args and Logger so updater can read Args."""
        sys.argv = ["test", "publisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Reset Args."""
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}

    def test_column_index_to_letter(self) -> None:
        """Test _column_index_to_letter for A, B, Z, AA."""
        updater = GoogleSheetUpdater()
        self.assertEqual(updater._column_index_to_letter(1), "A")
        self.assertEqual(updater._column_index_to_letter(2), "B")
        self.assertEqual(updater._column_index_to_letter(26), "Z")
        self.assertEqual(updater._column_index_to_letter(27), "AA")

    def test_download_location_template(self) -> None:
        """Test DOWNLOAD_LOCATION_TEMPLATE format."""
        url = DOWNLOAD_LOCATION_TEMPLATE.format(workspace_id="239181")
        self.assertEqual(
            url,
            "https://www.datalumos.org/datalumos/project/239181/version/V1/view",
        )

    def test_find_row_by_url_exact_wins_over_earlier_prefix(self) -> None:
        """Exact URL row must win even if a shorter prefix appears first in the column."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        short_u = "https://data.cms.gov/provider-summary/a/b"
        long_u = "https://data.cms.gov/provider-summary/a/b-by-geography"
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [[short_u], [long_u]]
        }
        row = updater._find_row_by_url(
            mock_service, "sheet1", "CDC", "A", long_u
        )
        self.assertEqual(row, 3)

    def test_find_row_by_url_longest_prefix_when_no_exact(self) -> None:
        """With no exact row, choose the sheet row whose URL is the longest strict prefix of source."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        full = "https://data.cms.gov/a/b/c/d"
        mid = "https://data.cms.gov/a/b/c"
        short = "https://data.cms.gov/a/b"
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [[short], [mid]]
        }
        row = updater._find_row_by_url(mock_service, "sheet1", "CDC", "A", full)
        self.assertEqual(row, 3)

    def test_find_row_by_url_shortest_extension_when_source_prefix_of_cell(self) -> None:
        """When source is a strict prefix of sheet URLs, pick the shortest extending cell."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        src = "https://data.cms.gov/a/b"
        ext1 = "https://data.cms.gov/a/b/c"
        ext2 = "https://data.cms.gov/a/b/c/d"
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [[ext2], [ext1]]
        }
        row = updater._find_row_by_url(mock_service, "sheet1", "CDC", "A", src)
        self.assertEqual(row, 3)

    def test_find_row_by_url_no_match(self) -> None:
        """Unrelated URLs do not match via substring."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [["https://other.example.com/x"]]
        }
        row = updater._find_row_by_url(
            mock_service, "sheet1", "CDC", "A", "https://data.cms.gov/unrelated"
        )
        self.assertIsNone(row)

    def test_build_update_requests_formats_file_size(self) -> None:
        """Test _build_update_requests formats raw byte count as user-friendly size."""
        updater = GoogleSheetUpdater()
        column_map = {
            "URL": "A",
            "Claimed": "B",
            "Data Added": "C",
            "Download Location": "D",
            "Date Downloaded": "E",
            "Dataset Size": "F",
            "File extensions of data uploads": "G",
            "Metadata availability info": "H",
            "Dataset Download Possible?": "I",
            "Nominated to EOT / USGWDA": "J",
        }
        project = {"file_size": "10485760", "download_date": "2025-01-15", "extensions": "csv"}
        requests = updater._build_update_requests(
            "CDC", 2, column_map, "239181", project, "testuser", ""
        )
        dataset_size_requests = [r for r in requests if "F2" in r.get("range", "")]
        self.assertEqual(len(dataset_size_requests), 1)
        self.assertEqual(dataset_size_requests[0]["values"], [["10.0 MB"]])

    def test_build_update_requests_prepends_url_for_new_row(self) -> None:
        """When source_url_for_new_row is set, URL column is written first."""
        updater = GoogleSheetUpdater()
        column_map = {
            "URL": "A",
            "Claimed": "B",
            "Data Added": "C",
            "Download Location": "D",
            "Date Downloaded": "E",
            "Dataset Size": "F",
            "File extensions of data uploads": "G",
            "Metadata availability info": "H",
            "Dataset Download Possible?": "I",
            "Nominated to EOT / USGWDA": "J",
        }
        project = {"download_date": "2025-01-15", "extensions": "csv"}
        requests = updater._build_update_requests(
            "CDC",
            5,
            column_map,
            "999",
            project,
            "u",
            "https://example.com/new",
        )
        self.assertTrue(requests[0]["range"].startswith("CDC!A5"))
        self.assertEqual(requests[0]["values"], [["https://example.com/new"]])

    def test_get_next_append_row_counts_url_column(self) -> None:
        """Next append row is 2 + number of returned URL cells."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [["https://a.com"], ["https://b.com"]]
        }
        r = updater._get_next_append_row(mock_service, "sid", "Tab1", "A")
        self.assertEqual(r, 4)

    def test_get_next_append_row_empty_below_header(self) -> None:
        """Empty URL column means first data row is 2."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {}
        r = updater._get_next_append_row(mock_service, "sid", "Tab1", "A")
        self.assertEqual(r, 2)

    @patch("publisher.GoogleSheetUpdater._GOOGLE_SHEETS_AVAILABLE", True)
    def test_update_missing_sheet_id(self) -> None:
        """Test update returns error when Args.google_sheet_id is empty."""
        updater = GoogleSheetUpdater()
        with patch.object(Args, "google_sheet_id", ""), patch.object(Args, "google_credentials", None):
            success, msg = updater.update("https://example.com", "123", {})
        self.assertFalse(success)
        self.assertIn("required", (msg or "").lower())

    @patch("publisher.GoogleSheetUpdater._GOOGLE_SHEETS_AVAILABLE", True)
    def test_update_missing_source_url(self) -> None:
        """Test update returns error when source_url is empty."""
        updater = GoogleSheetUpdater()
        cred = Path(tempfile.gettempdir()) / "nonexistent.json"
        with patch.object(Args, "google_sheet_id", "abc123"), patch.object(Args, "google_credentials", cred):
            success, msg = updater.update("", "123", {})
        self.assertFalse(success)
        self.assertIn("source url", (msg or "").lower())

    @patch("publisher.GoogleSheetUpdater._GOOGLE_SHEETS_AVAILABLE", False)
    def test_update_google_sheets_not_available(self) -> None:
        """Test update returns error when Google Sheets API is not installed."""
        updater = GoogleSheetUpdater()
        success, msg = updater.update("https://example.com", "123", {})
        self.assertFalse(success)
        self.assertIn("not installed", msg.lower())

    @patch("publisher.GoogleSheetUpdater._GOOGLE_SHEETS_AVAILABLE", True)
    def test_update_for_not_found_or_no_links_missing_sheet_id(self) -> None:
        """Test update_for_not_found_or_no_links returns error when sheet ID missing."""
        updater = GoogleSheetUpdater()
        with patch.object(Args, "google_sheet_id", ""), patch.object(Args, "google_credentials", None):
            success, msg = updater.update_for_not_found_or_no_links(
                "https://example.com", "Not found"
            )
        self.assertFalse(success)
        self.assertIn("required", (msg or "").lower())

    @patch("publisher.GoogleSheetUpdater._GOOGLE_SHEETS_AVAILABLE", False)
    def test_update_for_not_found_or_no_links_api_not_available(self) -> None:
        """Test update_for_not_found_or_no_links returns error when API not installed."""
        updater = GoogleSheetUpdater()
        success, msg = updater.update_for_not_found_or_no_links(
            "https://example.com", "No live links"
        )
        self.assertFalse(success)
        self.assertIn("not installed", (msg or "").lower())

    @skip_if_no_google
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_update_credentials_not_found(self, mock_from_sa: MagicMock) -> None:
        """Test update returns error when credentials file does not exist."""
        mock_from_sa.side_effect = FileNotFoundError()
        updater = GoogleSheetUpdater()
        cred = Path(tempfile.gettempdir()) / "nonexistent_creds.json"
        with patch.object(Args, "google_sheet_id", "abc"), patch.object(
            Args, "google_credentials", cred
        ), patch.object(Args, "google_sheet_name", "CDC"):
            success, msg = updater.update("https://example.com", "123", {})
        self.assertFalse(success)
        self.assertIn("not found", (msg or "").lower())

    @skip_if_no_google
    @patch("publisher.GoogleSheetUpdater.build_sheets_v4_service")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_update_success_mocked(
        self, mock_from_sa: MagicMock, mock_build: MagicMock
    ) -> None:
        """Test update success path with mocked Sheets API."""
        mock_creds = MagicMock()
        mock_creds.universe_domain = "googleapis.com"
        mock_from_sa.return_value = mock_creds
        mock_service = MagicMock()

        # First get: header row (CDC!1:1). Second get: URL column A2:A.
        header_response = {
            "values": [
                [
                    "URL",
                    "Claimed",
                    "Data Added",
                    "Download Location",
                    "Date Downloaded",
                    "Dataset Size",
                    "File extensions of data uploads",
                    "Metadata availability info",
                    "Dataset Download Possible?",
                    "Nominated to EOT / USGWDA",
                ]
            ]
        }
        url_column_response = {"values": [["https://example.com/data"], ["https://other.com"]]}
        mock_get = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get.execute.side_effect = [header_response, url_column_response]
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value.execute.return_value = {}

        mock_build.return_value = mock_service

        cred_path = Path(tempfile.gettempdir()) / "creds_pub_test.json"
        cred_path.write_text("{}")

        updater = GoogleSheetUpdater()
        with patch.object(Args, "google_sheet_id", "sheet123"), patch.object(
            Args, "google_credentials", cred_path
        ), patch.object(Args, "google_sheet_name", "CDC"), patch.object(Args, "google_username", "testuser"):
            success, msg = updater.update(
                "https://example.com/data",
                "239181",
                {
                    "download_date": "2025-01-15",
                    "file_size": "10 MB",
                    "extensions": "csv, zip",
                },
            )

        cred_path.unlink(missing_ok=True)

        self.assertTrue(success)
        self.assertIsNone(msg)
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once()

    @skip_if_no_google
    @patch("publisher.GoogleSheetUpdater.build_sheets_v4_service")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_update_appends_when_no_url_match(
        self, mock_from_sa: MagicMock, mock_build: MagicMock
    ) -> None:
        """When no row matches, updates target the next append row and include URL."""
        mock_creds = MagicMock()
        mock_creds.universe_domain = "googleapis.com"
        mock_from_sa.return_value = mock_creds
        mock_service = MagicMock()

        header_response = {
            "values": [
                [
                    "URL",
                    "Title",
                    "Agency",
                    "Office",
                    "Claimed",
                    "Data Added",
                    "Download Location",
                    "Date Downloaded",
                    "Dataset Size",
                    "File extensions of data uploads",
                    "Metadata availability info",
                    "Dataset Download Possible?",
                    "Nominated to EOT / USGWDA",
                ]
            ]
        }
        other_only = {"values": [["https://other-only.example/row"]]}
        mock_get = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get.execute.side_effect = [header_response, other_only, other_only]
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value.execute.return_value = {}

        mock_build.return_value = mock_service

        cred_path = Path(tempfile.gettempdir()) / "creds_pub_append_test.json"
        cred_path.write_text("{}")

        updater = GoogleSheetUpdater()
        with patch.object(Args, "google_sheet_id", "sheet123"), patch.object(
            Args, "google_credentials", cred_path
        ), patch.object(Args, "google_sheet_name", "CDC"), patch.object(Args, "google_username", "testuser"):
            success, msg = updater.update(
                "https://brand-new.example/page",
                "239181",
                {
                    "title": "Appended Row Title",
                    "agency": "HHS",
                    "office": "OASH",
                    "download_date": "2025-01-15",
                    "file_size": "1024",
                    "extensions": "csv",
                },
            )

        cred_path.unlink(missing_ok=True)

        self.assertTrue(success)
        self.assertIsNone(msg)
        batch = mock_service.spreadsheets.return_value.values.return_value.batchUpdate
        batch.assert_called_once()
        body = batch.call_args[1]["body"]
        data = body["data"]
        ranges = [d["range"] for d in data]
        self.assertTrue(any("CDC!A3" in r for r in ranges))
        url_vals = [d for d in data if "CDC!A3" in d.get("range", "")]
        self.assertEqual(url_vals[0]["values"], [["https://brand-new.example/page"]])
        b3 = [d for d in data if "CDC!B3" in d.get("range", "")]
        self.assertEqual(b3[0]["values"], [["Appended Row Title"]])
        c3 = [d for d in data if "CDC!C3" in d.get("range", "")]
        self.assertEqual(c3[0]["values"], [["HHS"]])
        d3 = [d for d in data if "CDC!D3" in d.get("range", "")]
        self.assertEqual(d3[0]["values"], [["OASH"]])

    def test_read_cell_text_empty_and_trim(self) -> None:
        """_read_cell_text returns trimmed string or empty."""
        updater = GoogleSheetUpdater()
        mock_service = MagicMock()
        g = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        g.execute.side_effect = [
            {"values": []},
            {"values": [[]]},
            {"values": [["  x  "]]},
        ]
        self.assertEqual(
            updater._read_cell_text(mock_service, "s", "CDC", "B", 2), ""
        )
        self.assertEqual(
            updater._read_cell_text(mock_service, "s", "CDC", "B", 3), ""
        )
        self.assertEqual(
            updater._read_cell_text(mock_service, "s", "CDC", "B", 4), "x"
        )

    def test_build_update_requests_writes_title(self) -> None:
        """title_to_write, agency_to_write, office_to_write populate optional columns."""
        updater = GoogleSheetUpdater()
        column_map = {
            "URL": "A",
            "Title": "B",
            "Agency": "C",
            "Office": "D",
            "Claimed": "E",
            "Data Added": "F",
            "Download Location": "G",
            "Date Downloaded": "H",
            "Dataset Size": "I",
            "File extensions of data uploads": "J",
            "Metadata availability info": "K",
            "Dataset Download Possible?": "L",
            "Nominated to EOT / USGWDA": "M",
        }
        project = {"download_date": "2025-01-15", "extensions": "csv"}
        req = updater._build_update_requests(
            "CDC",
            2,
            column_map,
            "1",
            project,
            "u",
            "",
            "The Dataset Name",
            "CMS",
            "Office of Data",
        )
        title_req = [r for r in req if "B2" in r.get("range", "")]
        self.assertEqual(len(title_req), 1)
        self.assertEqual(title_req[0]["values"], [["The Dataset Name"]])
        c2 = [r for r in req if "C2" in r.get("range", "")]
        self.assertEqual(c2[0]["values"], [["CMS"]])
        d2 = [r for r in req if "D2" in r.get("range", "")]
        self.assertEqual(d2[0]["values"], [["Office of Data"]])

    @skip_if_no_google
    @patch("publisher.GoogleSheetUpdater.build_sheets_v4_service")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_update_matched_fills_title_when_empty(
        self, mock_from_sa: MagicMock, mock_build: MagicMock
    ) -> None:
        """When optional metadata columns are blank, values come from the project record."""
        mock_creds = MagicMock()
        mock_creds.universe_domain = "googleapis.com"
        mock_from_sa.return_value = mock_creds
        mock_service = MagicMock()
        header_response = {
            "values": [
                [
                    "URL",
                    "Title",
                    "Agency",
                    "Office",
                    "Claimed",
                    "Data Added",
                    "Download Location",
                    "Date Downloaded",
                    "Dataset Size",
                    "File extensions of data uploads",
                    "Metadata availability info",
                    "Dataset Download Possible?",
                    "Nominated to EOT / USGWDA",
                ]
            ]
        }
        url_column_response = {"values": [["https://example.com/data"], ["https://other.com"]]}
        title_cell_empty = {"values": [[]]}
        mock_get = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get.execute.side_effect = [
            header_response,
            url_column_response,
            title_cell_empty,
            title_cell_empty,
            title_cell_empty,
        ]
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value.execute.return_value = {}
        mock_build.return_value = mock_service

        cred_path = Path(tempfile.gettempdir()) / "creds_title_test.json"
        cred_path.write_text("{}")

        updater = GoogleSheetUpdater()
        with patch.object(Args, "google_sheet_id", "sheet123"), patch.object(
            Args, "google_credentials", cred_path
        ), patch.object(Args, "google_sheet_name", "CDC"), patch.object(Args, "google_username", "u"):
            success, msg = updater.update(
                "https://example.com/data",
                "99",
                {
                    "title": "Metadata Title",
                    "agency": "Agency X",
                    "office": "Office Y",
                    "download_date": "2025-01-15",
                    "file_size": "1",
                    "extensions": "csv",
                },
            )
        cred_path.unlink(missing_ok=True)
        self.assertTrue(success)
        self.assertIsNone(msg)
        body = mock_service.spreadsheets.return_value.values.return_value.batchUpdate.call_args[1][
            "body"
        ]
        b2 = [d for d in body["data"] if "CDC!B2" in d.get("range", "")]
        self.assertEqual(b2[0]["values"], [["Metadata Title"]])
        c2 = [d for d in body["data"] if "CDC!C2" in d.get("range", "")]
        self.assertEqual(c2[0]["values"], [["Agency X"]])
        d2 = [d for d in body["data"] if "CDC!D2" in d.get("range", "")]
        self.assertEqual(d2[0]["values"], [["Office Y"]])
